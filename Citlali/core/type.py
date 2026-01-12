from enum import Enum


class ListenerType(Enum):
    ON_CALLED = 1
    ON_NOTIFIED = 2

class MessageType(Enum):
    REQUEST = 1
    RESPONSE = 2
    NOTIFICATION = 3