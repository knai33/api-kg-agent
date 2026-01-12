import asyncio

from loguru import logger

from ..core.worker_keeper import WorkerKeeper
from ..core.type import ListenerType
from .entity import MessageParcel


class ChannelKeeper:
    def __init__(self, worker_keeper: WorkerKeeper):
        self._channels = dict()
        self._worker_keeper = worker_keeper

    def subscribe(self, worker_name, channels):
        for channel in channels:
            if channel not in self._channels:
                self._channels[channel] = []
            self._channels[channel].append(worker_name)

    def get_in_channel_workers(self, channel):
        if channel in self._channels:
            return self._channels[channel]
        else:
            logger.error(f"Channel {channel} not found")
            return None

    def _build_publish_task(self, message, message_content, channel):
        async def _publish_task(worker):
            return await worker.listen(ListenerType.ON_NOTIFIED, message, message_content, channel)
        return _publish_task

    async def publish(self, message_parcel: MessageParcel):
        worker_list = self.get_in_channel_workers(message_parcel.recipient)
        publish_task_list = []
        if worker_list is not None:
            for worker_name in worker_list:
                worker = self._worker_keeper.get_worker(worker_name)
                if worker is not None:
                    publish_task_list.append(self._build_publish_task(
                        message_parcel.message,
                        message_parcel.message_context,
                        message_parcel.recipient)(worker))
            await asyncio.gather(*publish_task_list)