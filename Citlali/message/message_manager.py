import asyncio
from asyncio import Queue

from loguru import logger

from ..core.worker_keeper import WorkerKeeper
from ..core.type import MessageType, ListenerType
from .channel_keeper import ChannelKeeper
from .entity import MessageParcel


class MessageManager:
    def __init__(self, worker_keeper: WorkerKeeper):
        self._queue: [MessageParcel] = Queue()
        self._worker_keeper = worker_keeper

        self._channel_keeper = ChannelKeeper(self._worker_keeper)

    def subscribe(self, worker_name, channels):
        return self._channel_keeper.subscribe(worker_name, channels)

    def start_listen(self):
        async def _run():
            while True:
                message_parcel = await self._queue.get()
                await self.on_message(message_parcel)
        asyncio.create_task(_run())

    async def stop_listen_when_idle(self):
        await self._queue.join()

    async def put_message(self, message, recipient, sender, message_type: MessageType):
        # 仅在MessageType.REQUEST时有Reply
        reply_callback = asyncio.get_event_loop().create_future() if message_type is MessageType.REQUEST else None

        message_parcel = MessageParcel(message, recipient, sender, message_type, reply_callback)
        await self._queue.put(message_parcel)
        return reply_callback if message_type is MessageType.REQUEST else None

    async def on_message(self, message_parcel):
        logger.debug("HANDLE MESSAGE: {}", message_parcel)
        match message_parcel.message_context.type:
            case MessageType.REQUEST:
                asyncio.create_task(self._call(message_parcel))
            case MessageType.NOTIFICATION:
                asyncio.create_task(self._notice(message_parcel))
            case MessageType.RESPONSE:
                asyncio.create_task(self._reply(message_parcel))

    async def _reply(self, message_parcel):
        message_parcel.reply_callback.set_result(message_parcel.message)

    async def _call(self, message_parcel):
        worker = self._worker_keeper.get_worker(message_parcel.recipient)
        if worker is not None:
            reply = await worker.listen(ListenerType.ON_CALLED, message_parcel.message, message_parcel.message_context)
            await self._queue.put(MessageParcel(message=reply,
                                                recipient=message_parcel.message_context.sender,
                                                sender=message_parcel.recipient,
                                                type=MessageType.RESPONSE,
                                                reply_callback=message_parcel.reply_callback))
        else:
            return None

    async def _notice(self, message_parcel):
        await self._channel_keeper.publish(message_parcel)
