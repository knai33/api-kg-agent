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

        def __init__(self, runtime, name) -> None:
            super().__init__(runtime, name)
            self.a = None
            self.event = asyncio.Event()

        @listener(ListenerType.ON_CALLED, listen_filter=lambda message: message.source == "call_01")
        async def on_call_1(self, message: Message, message_context):
            await asyncio.sleep(1)
            print(f"TestAgent 1 received message (Call01): {message.message}")

            await self.event.wait()
            return self.a

        @listener(ListenerType.ON_NOTIFIED, channel="test_channel")
        async def on_call_2(self, message: Message, message_context):
            await asyncio.sleep(5)
            self.a = message.message
            self.event.set()

    class TestAgent2(Agent):
        @listener(ListenerType.ON_NOTIFIED, channel="test_channel")
        async def on_call_2(self, message: Message, message_context):
            a = await runtime.call("test_agent", Message("TestMessage01!", "call_01"))
            print("XXX"+await a)

    runtime = CitlaliRuntime()
    runtime.run()
    test_agent = runtime.register(lambda: TestAgent(runtime, "test_agent"))
    test_agent2 = runtime.register(lambda: TestAgent2(runtime,"test_agent2"))

    await runtime.publish("test_channel", Message("TestPublishMessage!",""))
    await runtime.stop()

if __name__ == '__main__':
    asyncio.run(main())
