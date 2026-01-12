import uuid
from asyncio import Future
from datetime import datetime
from typing import Any

from ..core.type import MessageType


class MessageContext:
    mid: int
    build_time: float
    type: MessageType
    sender: str | None

class MessageParcel:
    message: Any
    recipient: str | None
    message_context: MessageContext
    reply_callback: Future

    def __init__(self, message: Any, recipient: str | None, sender: str | None, type: MessageType, reply_callback: Future) -> None:
        self.message = message
        self.recipient = recipient
        self.message_context = MessageContext()
        self.message_context.mid = uuid.uuid4().int
        self.message_context.build_time = datetime.now().timestamp()
        self.message_context.type = type
        self.message_context.sender = sender
        self.reply_callback = reply_callback

    def __str__(self) -> str:
        return (f"TYPE:{self.message_context.type} | "
                f"FROM:{self.message_context.sender} | "
                f"TO:{self.recipient} | "
                f"MSG:{self.message} ")
