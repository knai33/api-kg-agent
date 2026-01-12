import json
import re

from loguru import logger

from Citlali.core.agent import Agent
from Citlali.core.type import ListenerType
from Citlali.core.worker import listener
from Citlali.models.entity import ChatMessage

from Citlali.utils.image import Image
from PIL import Image as PILImage

from Fairy.message_entity import EventMessage, CallMessage
from Fairy.type import EventType, EventStatus, CallType, MemoryType


class ApiDescribeAgent(Agent):
    def __init__(self, runtime, model_client, neo4j_parser, file_path) -> None:
        system_messages = [ChatMessage(
            content="You are an experienced full-stack developer with over eight years of front-end and back-end development experience. You are proficient in various front-end page design and implementation techniques as well as back-end development. You also possess strong data analysis skills, enabling you to infer API description , parameter description and response description from provided api information (including JSON data and screenshots).",
            type="SystemMessage")]
        super().__init__(runtime, "ApiDescribeAgent", model_client, system_messages)
        self.init_plan = False

        # 初始化 Neo4j Parser（单例）
        self.neo4j_parser = neo4j_parser
        self.file_path = file_path

    def load_json_data(self):
        with open(self.file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @listener(ListenerType.ON_NOTIFIED, channel="app_channel",
              listen_filter=lambda msg: msg.event == EventType.Plan and msg.status == EventStatus.CREATED)
    async def on_plan_init(self, message: EventMessage, message_context):
        logger.info("[Describe] TASK in progress...")

        self.init_plan = True
        instruction = message.event_content

        # 读取 JSON 数据（从文件或硬编码）
        json_data = self.load_json_data()  # 假设这个方法加载 output.json 数据

        # 存储所有分析结果
        all_analysis_results = []
        # 遍历所有数据项，并记录前一个 item 的 filename 作为上一张截图
        all_images = [f"{item['filename']}" for item in json_data]

        # 遍历所有数据项
        for idx, item in enumerate(json_data):
            if not item.get("api_list"):  # 跳过 api_list 为空的数据
                continue

            current_image_path = all_images[idx]  # 当前项截图路径
            previous_image_path = all_images[idx - 1] if idx > 0 else None  # 上一项截图路径（不管是否有 api_list）

            # 构建 prompt，并准备图像输入
            has_previous_screenshot = previous_image_path is not None

            # 每个 API 单独处理
            for api in item["api_list"]:
                # 构造仅包含当前 API 的临时数据结构
                single_api_data = {
                    **{k: v for k, v in item.items() if k != "api_list"},
                    "api_list": [api]  # 只包含当前 API
                }
                prompt = self.build_init_prompt(single_api_data, has_previous_screenshot)

                # 准备图像列表：先加入上一张截图（如果有）
                images = []
                if has_previous_screenshot:
                    images.append(Image(PILImage.open(previous_image_path)))  # 上一张截图

                images.append(Image(PILImage.open(current_image_path)))  # 当前截图

                # 请求 LLM
                api_description_res = await self.request_llm(prompt, images)

                self.neo4j_parser.update_single_api_description(api_description_res)
                logger.info("成功更新单个 API 描述信息到 Neo4j")

                # 记录当前分析结果
                all_analysis_results.append({
                    "item": item,
                    "api_description_res": api_description_res,
                })

        # # 发布Plan事件
        # await self.publish("app_channel", EventMessage(EventType.Plan, EventStatus.DONE, plan_event_content))
        # logger.info("[Plan(First Run)] TASK completed.")


    @staticmethod
    def build_init_prompt(json_data, has_previous_screenshot) -> str:
        prompt = ""
        prompt += f"Task Objective:\n" \
                  f"Given the provided JSON data and current page screenshot, infer the API description, parameter description and response description. If a previous page screenshot is available, use it to observe UI changes and improve accuracy.\n" \
                  f"\n" \
                  f"Input:\n" \
                  f"1.JSON Data: Contains URL, method, parameters, response data, and HTML info.\n" \
                  f"2.Current Page Screenshot: UI state after the user interaction.\n"
        if has_previous_screenshot:
            prompt += f"3.Previous Page Screenshot: UI state before interaction \n"
        else:
            prompt += f"3.Previous Page Screenshot: Not available for the first step.\n"

        prompt += f"Output Requirements:\n" \
                  f"1. API Description:\n" \
                  f"   - Summarize purpose with URL and method.\n" \
                  f"   - Identify business function and module.\n" \
                  f"   - Only keep the **path portion** of the URL.\n" \
                  f"   - **Contextualize the operation within the business process** by identifying the user action that triggers this API (e.g., 'This API is called when a user cancels a pending leave application').\n" \
                  f"2. API Template:\n" \
                  f"   - A generalized version of the API path where dynamic parameters (unique identifiers, variables) in the path are replaced with {{ParameterName}}.\n" \
                  f"   - ParameterName is inferred from context (e.g., if the path is like '/Account/687de4c9d133ac53e/add', the template is '/Account/{{AccountID}}/add' where 'AccountID' is inferred from the preceding 'Account' segment).\n" \
                  f"   - If the path has no dynamic parameters, the template is identical to 'api_path'.\n" \
                  f"3. Parameter Descriptions:\n" \
                  f"   - For each parameter (from path, query string or post data):\n" \
                  f"     a) name: Extracted parameter name or the parameter name inferred from context for the dynamic path segment.\n" \
                  f"     b) description: Business meaning in context, including its role in the user action (e.g., 'ID of the leave application to be canceled').\n" \
                  f"     c) location: Where the parameter is placed, with values 'path' (for dynamic path segments), 'query' (for query string parameters), or 'body' (for request body parameters).\n" \
                  f"     d) required: Whether the parameter is required.(Can be determined from the 'required' attribute of HTML, if not, set to empty)\n" \
                  f"     e) dynamic_value: The specific value of the parameter in the current API request (e.g., for a path parameter 'AccountID' in '/Account/687de4c9d133ac53e/add', dynamic_value is '687de4c9d133ac53e').If the parameter is not dynamic (e.g., fixed query parameters or static body fields), dynamic_value must be set to empty value ''.\n"\
                  f"3. Response Description:\n" \
                  f"   - Explain the response structure (boolean/object/array) and its purpose **within the triggered business scenario**.\n" \
                  f"   - **Example Structure**: 'JSON object indicates the success or failure of [user action], including [key information] for [specific purpose]'.\n" \
                  f"   - Example (for reference only - replace with actual scenario): If the API is for submitting a reimbursement request,\n" \
                  f"     the response could be: 'JSON object indicates whether the reimbursement application was successfully submitted, including submission timestamp and approval status code'.\n" \
                  f"4. Output Formatting:\n" \
                  f"   - JSON with 'api_method', 'api_path', 'api_template', 'api_description', 'parameters', 'response_description' keys.\n" \
                  f"   - 'parameters' is an array of objects, each containing 'name', 'description', 'location', 'required'.\n" \
                  f"   - Make sure this JSON can be loaded correctly by json.load().!!\n" \
                  f"   - No other information is required besides JSON data!!\n"
        prompt += f"""
                    5. Output Example:
                    {{
                    {{
                    
                      "api_method": "GET",
                      "api_path": "/api/v1/hello",
                      "api_template": "/api/v1/hello"
                      "api_description": "description about the api",
                      "parameters": [
                        {{
                          "name": "parameter_a",
                          "description": "description about the parameter",
                          "location": "query",
                          "required": true,
                          "dynamic_value": ""
                        }}
                        ...
                      ],
                      "response_description": "description about the response"
                    }},
                    {{
                      "api_method": "GET",
                      "api_path": "/Account/687de4c9d133ac53e/add",
                      "api_template": "/Account/{{AccountID}}/add"
                      "api_description": "description about the api",
                      "parameters": [
                        {{
                          "name": "AccountID",
                          "description": "description about the parameter",
                          "location": "path",
                          "required": true,
                          "dynamic_value": "687de4c9d133ac53e"
                        }}
                        ...
                      ],
                      "response_description": "description about the response"
                    }}
                    }}
                   """

        prompt += f"Ensure that you understand the above requirements and begin analyzing the following data:\n" \
          f"JSON Data: {json_data}\n"

        return prompt

    def parse_response(self, response: str):
        print(response)

        if "json" in response:
            response = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL).group(1)
        response_json = json.loads(response)

        # 提取关键信息
        api_method = response_json.get("api_method")
        api_path = response_json.get("api_path")
        api_template = response_json.get("api_template")
        api_desc = response_json.get("api_description")
        parameters = response_json.get("parameters", [])
        response_description = response_json.get("response_description")

        # 构造返回结果
        return {
            "api_method": api_method,
            "api_path": api_path,
            "api_template": api_template,
            "api_description": api_desc,
            "parameters": parameters,
            "response_description": response_description
        }
