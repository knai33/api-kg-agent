from collections.abc import Callable
from typing import cast, runtime_checkable, Protocol

from .runtime import CitlaliRuntime
from .type import ListenerType, MessageType


def listener(listener_type, listen_filter=None, channel=None):
    def decorator(func):
        _listener = cast(WorkerListener, func)
        _listener.listener_type = listener_type
        if listener_type == ListenerType.ON_NOTIFIED and channel is None:
            raise ValueError("Channel must be specified for ON_NOTIFIED listener")
        else:
            _listener.channel = channel
        _listener.listen_filter = listen_filter
        return _listener
    return decorator

class Worker():
    def __init__(self, runtime: CitlaliRuntime, name, desc=None):
        self.name = name
        self.desc = desc
        self._message_manager = runtime.message_manager
        self._listeners = self._discover_listeners()

    @classmethod
    def _discover_listeners(cls):
        listeners = {
            ListenerType.ON_CALLED: [],
            ListenerType.ON_NOTIFIED: []
        }
        for attr in dir(cls):
            attr = getattr(cls, attr)
            if isinstance(attr, WorkerListener):
                listeners[attr.listener_type].append(attr)
        return listeners

    def get_notify_channel(self):
        channel = set()
        for notify_listener in self._listeners[ListenerType.ON_NOTIFIED]:
            channel.add(notify_listener.channel)
        return channel

    async def listen(self, listener_type, message, message_context, channel=None):
        match listener_type:
            case ListenerType.ON_CALLED:
                for listener in self._listeners[listener_type]:
                    if listener.listen_filter is None or listener.listen_filter(message):
                        return await listener(self, message, message_context)
            case ListenerType.ON_NOTIFIED:
                for listener in self._listeners[listener_type]:
                    if listener.channel == channel and (listener.listen_filter is None or listener.listen_filter(message)):
                        return await listener(self, message, message_context)

    async def call(self, worker_name, message):
        return await self._message_manager.put_message(message, worker_name, self.name, MessageType.REQUEST)

    async def publish(self, channel, message):
        await self._message_manager.put_message(message, channel, self.name, MessageType.NOTIFICATION)

@runtime_checkable
class WorkerListener(Protocol):
    listener_type: ListenerType
    listen_filter: Callable
    channel: str

    @staticmethod
    async def __call__(worker: Worker, message):
        ...