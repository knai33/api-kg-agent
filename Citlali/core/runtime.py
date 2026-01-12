from .worker_keeper import WorkerKeeper
from ..core.type import MessageType
from ..message.message_manager import MessageManager


class CitlaliRuntime:
    def __init__(self):
        super().__init__()
        self.workers = WorkerKeeper()
        self.message_manager = MessageManager(self.workers)

    # Singleton pattern
    def __new__(cls, *args, **kwargs):
        if not hasattr(CitlaliRuntime, "_instance"):
            CitlaliRuntime._instance = object.__new__(cls)
        return CitlaliRuntime._instance

    def get_instance(*args, **kwargs):
        if not hasattr(CitlaliRuntime, '_instance'):
            return CitlaliRuntime(*args, **kwargs)
        return CitlaliRuntime._instance

    def run(self):
        self.message_manager.start_listen()

    async def stop(self):
        await self.message_manager.stop_listen_when_idle()

    def register(self, worker):
        worker_instance=self.workers.register(worker)
        self.message_manager.subscribe(worker_instance.name, worker_instance.get_notify_channel())

    async def call(self, worker_name, message):
        return await self.message_manager.put_message(message, worker_name, None, MessageType.REQUEST)

    async def publish(self, channel, message):
        await self.message_manager.put_message(message, channel, None, MessageType.NOTIFICATION)