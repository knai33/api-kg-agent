import asyncio
import os

from loguru import logger

from Citlali.core.agent import Agent
from Citlali.core.runtime import CitlaliRuntime
from Citlali.core.type import ListenerType
from Citlali.core.worker import listener
from Citlali.models.entity import ChatMessage
from Citlali.models.openai.client import OpenAIChatClient


os.environ["OPENAI_API_KEY"] = "sk-8t4sGAakvPVKfFLn9801056499284a66B31aC07b1f9907F3"
os.environ["OPENAI_BASE_URL"] = "https://vip.apiyi.com/v1"


class Message:
    def __init__(self, content):
        self.content = content

class SimpleAgent(Agent):
    def __init__(self, runtime,name,desc) -> None:
        super().__init__(runtime,name,desc)
        self._system_messages = [ChatMessage(
            content="You are a helpful AI assistant.",
            type="SystemMessage")]
        self._model_client = OpenAIChatClient({
            'model': "gpt-4o-2024-11-20"
        })

    @listener(ListenerType.ON_CALLED, listen_filter=lambda msg: True)
    async def on_user_message(self, message: Message, message_context):
        user_message = ChatMessage(content=message.content,type="UserMessage", source="user")
        response = await self._model_client.create(
            self._system_messages + [user_message]
        )
        return Message(content=response.content)

async def main():
    logger.debug("[EXAMPLE] Simple Agent Running!")
    runtime = CitlaliRuntime()
    runtime.run()
    runtime.register(lambda: SimpleAgent(runtime, "simple_agent","A simple agent"))

    example = "Hello, how are you?"
    logger.info("User Say:" + example)
    result = await runtime.call("simple_agent", Message(example))
    logger.info("Agent Say:" + (await result).content)

    await runtime.stop()

if __name__ == '__main__':
    asyncio.run(main())