import json
import re
from urllib.parse import urlparse

from loguru import logger

from Citlali.core.agent import Agent
from Citlali.core.type import ListenerType
from Citlali.core.worker import listener
from Citlali.models.entity import ChatMessage

from Citlali.utils.image import Image
from PIL import Image as PILImage

from Fairy.message_entity import EventMessage, CallMessage
from Fairy.type import EventType, EventStatus, CallType, MemoryType


class ApiDependencyAgent(Agent):
    def __init__(self, runtime, model_client, neo4j_parser, file_path) -> None:
        system_messages = [ChatMessage(
            content="You are an experienced full-stack developer with over eight years of front-end and back-end development experience. You are proficient in various front-end page design and implementation techniques as well as back-end development. You also possess strong data analysis skills, enabling you to infer API dependency from provided api information .",
            type="SystemMessage")]
        super().__init__(runtime, "ApiDependencyAgent", model_client, system_messages)
        self.init_plan = False

        # 初始化 Neo4j Parser（单例）
        self.neo4j_parser = neo4j_parser
        self.file_path = file_path

    def load_json_data(self):
        """
        加载 output.json 文件中的数据。
        """
        with open(self.file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @listener(ListenerType.ON_NOTIFIED, channel="app_channel",
              listen_filter=lambda msg: msg.event == EventType.Plan and msg.status == EventStatus.CREATED)
    async def on_plan_init(self, message: EventMessage, message_context):
        logger.info("[ApiDependency] TASK in progress...")

        # 读取 JSON 数据（从文件或硬编码）
        json_data = self.load_json_data()
        prompt = self.build_init_prompt(json_data)
        api_dependency_res = await self.request_llm(prompt)
        print(api_dependency_res)
        self.neo4j_parser.update_api_dependency(api_dependency_res)
        logger.info("成功更新全部 API 间依赖信息到 Neo4j")

        # # 记录当前分析结果
        # all_analysis_results.append({
        #     "item": current_api,
        #     "api_description_res": api_dependency_res,
        # })

        # # 发布Plan事件
        # await self.publish("app_channel", EventMessage(EventType.Plan, EventStatus.DONE, plan_event_content))
        # logger.info("[Plan(First Run)] TASK completed.")

        # print(all_analysis_results)
        self.init_plan = False

    @staticmethod
    def build_init_prompt(json_data) -> str:
        prompt = ""
        prompt += f'''
                  Task Objective:\n
                  1. First, infer the **user's core operation intent** from the provided API sequence (e.g., "add a new record", "change user status", "search and modify data").
                  2. Based on this intent, determine the **logically necessary API sequence** required to complete the operation. A dependency exists only if an API is mandatory for completing the core operation (excluding APIs unrelated to the intent).
                  Input:\n
                  API Request Data containing url, method, parameters, response_data (with timestamps).
                  '''
        prompt += f'''
                    Analysis Steps and Rules:\n
                    1. **Infer Core Operation Intent**:
                        - Analyze API functions (from url/method/parameters) and their sequence to determine the user's goal. Examples:
                            - If APIs are "check-name → add-data → get-list", the intent is "add a new data record".
                            - If APIs are "search-user-list → change-user-status", the intent is "search for a user and change their status".
                    2. **Identify Operation-Related APIs**:
                        - Include only APIs directly involved in achieving the core intent. Exclude APIs that are merely "side effects" (e.g., "get-list" after "add-data" is a side effect of displaying results, not required to complete "adding").
                    3. **Determine Necessary Dependencies in Sequence**:
                        - For APIs related to the core intent, check if they rely on prior APIs (via parameter association or logical prerequisites, including nested parameters).
                        - The sequence must reflect "what is required to complete the operation", not just time order.                 
                    4. **Exclude Unrelated APIs**:
                        - If an API is not required to achieve the core intent (even if executed in sequence), it has no dependencies with the operation-related APIs.
                    Dependency Analysis Tips:\n
                    1. **Semantic Parameter Name Association**:
                    - If an API (B) uses a parameter with a name semantically related to a preceding API's resource (e.g., "menuId" in B vs. "menuTree" in A), **suspect a dependency**.
                    - Examples of semantic matches:
                        - "menuId" → "menuTree", "roleId" → "roleList", "deptId" → "deptTree".
                        - Plural/singular variations (e.g., "menus" → "menuId") count as matches.
                    2. **Value Validation for Suspected Dependencies**:
                    - For semantically associated parameters (e.g., "menuId" from B), check if their values (e.g., "1,101,1007") exactly match identifiers in the preceding API's response (e.g., "id":1, "id":101 in A's menu tree).
                    - If values match, confirm the dependency; if not, discard.
                    3. **Explicit Handling of Comma-Separated Values**:
                    - Treat comma-separated parameters (e.g., "menuIds=1,101") as individual values to be matched against the preceding API's response.
            
                     Output Formatting:\n 
                    - JSON with "api_dependency" (the necessary sequence for the core operation) and "reason" (including inferred intent and why each API is required).                    - Make sure this JSON can be loaded correctly by json.load().!!\n
                    - If the sequence has three or more APIs (e.g., A→B→C),split it into pairwise direct dependencies(e.g., A->B, B->C).
                    - No other information is required besides JSON data!!\n            
        
                    Example 1 (Add operation):
                    Input APIs: "check-name → add-data → get-list"
                    {{
                      "api_dependency": [
                        "POST /check-name → POST /add-data"
                      ],
                      "reason": "User intent is 'add a new record'. To complete this, 'check-name' is required to verify (logical prerequisite), 'add-data' is the core action. 'get-list' is a side effect (display result) and not required for adding, so excluded."
                    }}
                    
                    Example 2 (Modify status operation):
                    Input APIs: "search-user-list → change-user-status"
                    {{
                      "api_dependency": [
                        "POST /system/user/list → POST /system/user/changeStatus"
                      ],
                      "reason": "User intent is 'search for a user and change their status'. To complete this, 'search-user-list' provides the 'userId' (parameter dependency) needed for 'change-user-status', so the sequence is required."
                    }}
                    '''
        prompt += f"Ensure that you understand the above requirements and begin analyzing the following data:\n" \
                  f"{json_data}\n"
        return prompt

    def parse_response(self, response: str):
        print(response)

        if "json" in response:
            response = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL).group(1)
        response_json = json.loads(response)

        # 提取关键信息
        parameters = response_json.get("api_dependency", [])

        # 构造返回结果
        return {
            "api_dependency": parameters,
        }
