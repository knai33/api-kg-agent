import os
import subprocess

from loguru import logger

from Citlali.core.runtime import CitlaliRuntime
from Citlali.models.openai.client import OpenAIChatClient

from Fairy.agents.api_describe_agent import ApiDescribeAgent
from Fairy.agents.param_analyze_agent import ParamAnalyzeAgent

from Fairy.agents.api_dependency_agent import ApiDependencyAgent
from Fairy.agents.api_agents.api_filter_agent import ApiFilterAgent
from Fairy.agents.api_agents.api_planner_agent import ApiPlannerAgent
from Fairy.agents.api_agents.api_execute_agent import ApiExecuteAgent
from Fairy.agents.api_agents.api_reflect_agent import ApiReflectAgent


from Fairy.fairy_config import Config
from Fairy.config.config import *
from Fairy.memory.api_memory import ApiMemory
from Fairy.memory.neo4j_api_data_parser import APIDataParser
from Fairy.message_entity import EventMessage
from Fairy.type import EventType, EventStatus

os.environ["OPENAI_API_KEY"] = "sk-zk2d9aae813fa366fafd3e4d9548327d66e68536902222b2"
os.environ["OPENAI_BASE_URL"] = "https://api.zhizengzeng.com/v1"

os.environ["ADB_PATH"] = "C:/Users/neosunjz/AppData/Local/Android/Sdk/platform-tools/adb.exe"

class FairyCore:
    def __init__(self):
        self._model_client = OpenAIChatClient({
            'model': "gpt-4o-2024-11-20",
            'temperature': 0
        })
        self._config = Config(adb_path=os.environ["ADB_PATH"])


    async def start(self, instruction):
        # await self.get_device()

        runtime = CitlaliRuntime()
        runtime.run()
        api_memory = ApiMemory()


        neo4j_parser = APIDataParser(APIDataParser_path, neo4j_url, neo4j_user, neo4j_password, nro4j_database)
        # runtime.register(lambda: ApiDescribeAgent(runtime, self._model_client, neo4j_parser, APIDataParser_path))
        # runtime.register(lambda: ParamAnalyzeAgent(runtime, self._model_client, neo4j_parser, APIDataParser_path))
        runtime.register(lambda: ApiDependencyAgent(runtime, self._model_client, neo4j_parser, APIDataParser_path))
        await runtime.publish("app_channel", EventMessage(EventType.Plan, EventStatus.CREATED, instruction))

        # runtime.register(lambda: ApiFilterAgent(runtime, self._model_client, api_memory, neo4j_parser))
        # runtime.register(lambda: ApiPlannerAgent(runtime, self._model_client, api_memory, neo4j_parser))
        # runtime.register(lambda: ApiExecuteAgent(runtime, self._model_client, api_memory, neo4j_parser))
        # runtime.register(lambda: ApiReflectAgent(runtime, self._model_client, api_memory, neo4j_parser))


        # runtime.register(lambda: KeyInfoExtractorAgent(runtime, self._model_client))
        # runtime.register(lambda: ShortTimeMemoryManager(runtime))

        # await runtime.publish("app_channel", EventMessage(EventType.Filter, EventStatus.CREATED, instruction))


        # api_memory.set_instruction("把我的账号状态设置为在线状态")
        # api_plan_res = [{'step1': {'method': 'POST', 'url': '/system/role/checkRoleNameUnique'}},
        #                 {'step2': {'method': 'POST', 'url': '/system/role/checkRoleKeyUnique'}}]
        # api_memory.set_total_plans(api_plan_res)
        # execute
        # await runtime.publish("app_channel", EventMessage(EventType.Plan, EventStatus.DONE, instruction))

        # reflect
        # await runtime.publish("app_channel", EventMessage(EventType.ActionExecution, EventStatus.CREATED, instruction))


        await runtime.stop()