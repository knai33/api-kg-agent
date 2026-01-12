import asyncio

from Citlali.core.agent import Agent
from Citlali.core.runtime import CitlaliRuntime
from Citlali.core.worker import listener
from Citlali.core.type import ListenerType

from loguru import logger

async def main():
    logger.debug("Running!")
    class Message:
        def __init__(self, message, source):
            self.message = message
            self.source = source

    class TestAgent(Agent):

        @listener(ListenerType.ON_CALLED, listen_filter=lambda message: message.source == "call_01")
        async def on_call_1(self, message: Message, message_context):
            await asyncio.sleep(1)
            print(f"TestAgent 1 received message (Call01): {message.message}")
            await asyncio.sleep(1)
            await self.publish("test_channel", "TestPublishMessage by Agent 1!")
            a = await self.call("test_agent2", Message("TestMessage02!", "call_02"))
            return "TestAgent response of 1(1) and " + await a

        @listener(ListenerType.ON_CALLED, listen_filter=lambda message: message.source == "call_02")
        async def on_call_2(self, message: Message, message_context):
            print(f"TestAgent 1 received message (Call02): {message.message}")
            return "TestAgent response of 1(2)"

    class TestAgent2(Agent):
        @listener(ListenerType.ON_CALLED, listen_filter=lambda message: message.source == "call_02")
        async def on_call_2(self, message: Message, message_context):
            print(f"TestAgent 2 received message (Call02): {message.message}")
            return "TestAgent response of 2"

    class TestAgent3(Agent):
        @listener(ListenerType.ON_NOTIFIED, channel="test_channel")
        async def on_receive(self, message, message_context):
            await asyncio.sleep(2)
            print(f"TestAgent 3 received message: {message}")

    runtime = CitlaliRuntime()
    runtime.run()
    test_agent = runtime.register(lambda: TestAgent(runtime, "test_agent"))
    test_agent2 = runtime.register(lambda: TestAgent2(runtime,"test_agent2"))
    test_agent3 = runtime.register(lambda: TestAgent3(runtime,"test_agent3"))
    a = await runtime.call("test_agent", Message("TestMessage01!", "call_01"))
    print(await a)
    await runtime.publish("test_channel", "TestPublishMessage!")
    await runtime.stop()

if __name__ == '__main__':
    asyncio.run(main())
