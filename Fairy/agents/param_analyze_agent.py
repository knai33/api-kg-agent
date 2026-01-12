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

class ParamAnalyzeAgent(Agent):
    def __init__(self, runtime, model_client, neo4j_parser, file_path) -> None:
        system_messages = [ChatMessage(
            content="You are an experienced full-stack developer with over eight years of front-end and back-end development experience. You are proficient in various front-end page design and implementation techniques as well as back-end development. You also possess strong data analysis skills, enabling you to analyze only request parameter source , parameter conversion detection and parameter constraint from provided api information (including JSON data and screenshots).",
            type="SystemMessage")]
        super().__init__(runtime, "ParamAnalyzeAgent", model_client, system_messages)
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
        logger.info("[Param Analyze] TASK in progress...")


        json_data = self.load_json_data()  # 假设这个方法加载 output.json 数据

        # 存储所有分析结果
        all_analysis_results = []
        # 遍历所有数据项，并记录前一个 item 的 filename 作为上一张截图
        all_screen_path = [f"{item['filename']}" for item in json_data]

        # 遍历所有数据项
        processed_data = []
        for idx, item in enumerate(json_data):
            if not item.get("api_list"):  # 跳过 api_list 为空的数据
                continue

            # 先构造出块式的数据，以防一个点有多个api
            for api in item["api_list"]:
                # 构造仅包含当前 API 的临时数据结构
                single_api_data = {
                    **{k: v for k, v in item.items() if k != "api_list"},
                    "api": api  # 只包含当前 API
                }
                processed_data.append(single_api_data)

        descriptions = self.neo4j_parser.get_api_param_description(processed_data)

        for i in range(len(processed_data)):
            current_api = processed_data[i]
            current_image_path = current_api['filename']  # 当前项截图路径
            idx = all_screen_path.index(current_image_path)
            previous_image_path = all_screen_path[idx - 1] if idx > 0 else None

            # 构建 prompt，并准备图像输入
            has_previous_screenshot = previous_image_path is not None
            images = []
            if has_previous_screenshot:
                images.append(Image(PILImage.open(previous_image_path)))  # 上一张截图

            # 准备图像列表：先加入上一张截图（如果有）
            images.append(Image(PILImage.open(current_image_path)))  # 当前截图

            # 获取当前元素之前的所有api描述
            previous_descriptions = descriptions[:i]

            # 如果是已经存在的节点，则附上已分析的数据
            analyzed_param = self.neo4j_parser.get_analyzed_api_param(current_api)
            has_analyzed_params = analyzed_param and (
                    analyzed_param[0]["source"] is not None or
                    analyzed_param[0]["conversion"] is not None
            )

            prompt = self.build_init_prompt(
                current_api,
                has_previous_screenshot,
                previous_descriptions,
                analyzed_param if has_analyzed_params else None
            )

            parameter_analysis = await self.request_llm(prompt, images)
            print(parameter_analysis)
            current_url = current_api["api"]["url"]
            current_path = urlparse(current_url).path
            current_method = current_api["api"]["method"]

            self.neo4j_parser.update_param_analysis(parameter_analysis, current_path, current_method)
            logger.info("成功更新API参数信息到 Neo4j")

            # 记录当前分析结果
            all_analysis_results.append({
                "item": current_api,
                "parameter_analysis": parameter_analysis,
            })

        self.init_plan = False

    @staticmethod
    def build_init_prompt(current_api, has_previous_screenshot, previous_descriptions, analyzed_param) -> str:
        prompt = ""
        prompt += f'''
                  Overall task:
                  Capture API information while operating the webpage, analyze and learn the API and its parameters, and then directly call the API to complete the task when performing similar tasks in the future.
                  Your Task Objective:" \
                  Analyze the provided API request data, historical API descriptions, screenshots, and HTML interactions to determine:
                    1.Parameter source (direct input / system preset / prefix API)"
                    2.Parameter conversion types (none/mapping/functional)
                    3.Parameter Constraint rules (type constraints and business rules)
                 **Note！！**: Only analyze parameters sent to the backend (request parameters). Do NOT analyze response parameters or fields in API response(response_body)!!!.
                 Example: there is a GET request with no explicit request parameters, just return an empty list instead of analyzing response content.
                  Input:
                    1.Current API Data: Contains URL, method, parameters, response data, and HTML info.
                    2.Historical API Descriptions: Text records of previous API requests and their parameter details.
                    3.Historical parameter analysis results of the same API(if exists): Including name, source, conversion, constraints, etc. for reference. Note: Previous analysis may contain errors; please combine current data for more comprehensive results.
                    4.Current Page Screenshot: UI state after the user interaction.
                  '''
        if has_previous_screenshot:
            prompt += f"5.Previous Page Screenshot: UI state before interaction \n"
        else:
            prompt += f"5.Previous Page Screenshot: Not available for the first step.\n"
        prompt += f'''
                    Analysis Rules:\n
                    1. Parameter Source (direct input / system preset / prefix API):\n
                        - Direct input: Parameters whose values are explicitly entered by the user through text input elements (e.g., typing into text boxes, input fields). These values are manually provided by the user and are not pre-defined options or system-generated. 
                          Examples include:
                            Email addresses typed into an input box.
                            Usernames entered in a text field.
                            Excludes: Values from selecting pre-set options (e.g., dropdowns, radio buttons), clicking buttons, or any action that does not involve manual text input of specific values.
                        - Indirect input: Parameters whose values are not directly entered by the user, but come from system pre-settings or prior API responses. Divided into two subcategories:
                         - System preset: Values from pre-defined system options or default settings, where the user only selects/triggeres them (not manually inputting the value itself). 
                            Examples include:
                              Options from dropdowns/radio buttons (e.g., gender options "Male/Female" pre-set by the system; sequence numbers "1/2/3" predefined in the system).
                              Default values automatically filled by the system (e.g., default date, pre-set initial values).
                         - Prefix API: Values obtained from the response data of previously called APIs, which are used in subsequent operations. 
                            Examples include:
                              when viewing an employee list, the initial list API returns employee information containing employeeId; 
                              when performing operations like editing or deleting an employee, the passed employeeId parameter comes from the previous list API
                            -- When applicable, include the API path in parentheses: e.g., "prefix API(GET /api/employees/list)".
                            -- Heuristic: If a parameter name contains "Id"/"ID" and its value is a long numerical string or UUID (not manually inputtable by the user), it is likely from a prefix API.
                        Determination Priority:
                            First determine if it is direct input (check if the value is manually typed into a text input element).
                            If not, check if it is system preset (value comes from pre-defined system options or default settings).
                            The remaining cases are classified as prefix API probably.
                        Key Distinction:
                            Direct input requires the user to manually type the specific value (the user "creates" the value).
                            Indirect input does not require manual typing: system preset values are "selected" from pre-existing options, and prefix API values are "referenced" from prior API responses. 
                    2.Parameter conversion types (none/mapping(system_mapping or prefix API mapping)/functional):\n
                    - None: Parameter value is used without modification, derivation, or mapping.\n
                      -- Includes raw user inputs, values from prefix APIs, or system default values that don't undergo further transformation.\n
                    - Mapping: Value is transformed via a predefined mapping:\n
                      - Prefix API mapping: Parameter value mapping relationships are derived from the response of previously called APIs.
                        -- In most cases, when the parameter name matches the previously called API and its response, there is likely to be a mapping relationship.
                        -- output_format: "prefix API mapping ([prefix API method] [prefix API name])"
                      - System mapping: Fixed mapping performed by the system's built-in dictionary.
                        -- All mapping relationships except for Prefix API mapping are system mappings,such as gender and status values set by the system.
                        -- output_format: "system_mapping"
                    - Functional: Value is obtained through calculation or function processing (e.g., age calculated based on date of birth, total amount calculated as quantity multiplied by unit price).\n
                    - Check if the parameter value is different from the original input (user input, prefix API value, or system default value) and determine the conversion type according to the above rules.\n
                    3.Parameter Constraint rules (type constraints and business rules):\n
                    - Type constraints: Infer from HTML input type (text→string, number→integer)\n
                    - Business constraints:\n
                       - Required fields (HTML's required attribute)\n
                       - Value ranges (e.g., age > 0)\n
                       - Discrete options (e.g., status=0/1)\n
                       - Example: "placeholder='please enter a positive integer'" implies positive integer constraint\n

                    Output Formatting:\n 
                    - JSON with 'parameter_analysis' , 'source reason' keys.\n
                    - 'parameter_analysis' is an array of objects,each incorporating four attributes: name, source, conversion, and constraints.\n
                    - 'parameter_analysis' can be empty because there are no parameters.
                    - Make sure this JSON can be loaded correctly by json.load().!!\n
                    - No other information is required besides JSON data!!\n            

                    Example Output:
                    {{
                      "parameter_analysis": [
                        {{
                          "name": "parameter_a",
                          "source": "direct input / system preset / prefix API",
                          "conversion": "none",
                          "constraints": ["string", "required"]
                        }},
                        {{
                          "name": "parameter_b",
                          "source": "prefix API(GET /api/list)",
                          "conversion": "none",
                          "constraints": ["string", "unique (validated by preceding API)"]
                        }},
                        {{
                          "name": "parameter_c",
                          "source": "prefix API (GET /xxx/xxx)",
                          "conversion": "prefix API mapping (GET /xxx/xxx)",
                          "constraints": ["integer", "positive number"]
                        }},
                        {{
                          "name": "parameter_d",
                          "source": "system preset",
                          "conversion": "system_mapping",
                          "constraints": ["integer"]
                        }}
                      ]
                      "source reason": Analysis of parameter sources
                    }}
                    '''

        prompt += f"Ensure that you understand the above requirements and begin analyzing the following data:\n" \
                  f"Current API : \n{current_api}\n" \
                  f"Historical API Descriptions: \n{previous_descriptions}\n"
        if analyzed_param:
            # 格式化历史参数分析结果，使其更易读
            param_text = "\n".join([
                f"- API Template: {param['api_template']}"
                f"- parameter name: {param['name']}, description: {param['desc']} \n"
                f"location={param['location']}, history_values:{param['history_values']}, source={param['source']}, conversion={param['conversion']}, constraints={param['constraints']}"
                for param in analyzed_param
            ])
            prompt += f"Historical parameter analysis results: \n{param_text}\n"
        return prompt

    def parse_response(self, response: str):
        print(response)

        if "json" in response:
            response = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL).group(1)
        response_json = json.loads(response)

        # 提取关键信息
        parameters = response_json.get("parameter_analysis", [])

        # 构造返回结果
        return {
            "parameter_analysis": parameters,
        }
