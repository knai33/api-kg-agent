from datetime import datetime

from Fairy.type import EventType, EventStatus, CallType


class EventMessage:
    def __init__(self, event: EventType, status: EventStatus, event_content=None):
        self.event = event
        self.status = status
        self.event_content = event_content
        self.timestamp = datetime.now().timestamp()

    def __str__(self):
        return f"EventMessage: {self.event}, {self.status}, {self.event_content}"

class CallMessage:
    def __init__(self, call: CallType, call_content=None):
        self.call = call
        self.call_content = call_content