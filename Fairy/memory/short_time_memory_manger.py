import asyncio

from loguru import logger

from Citlali.core.type import ListenerType
from Citlali.core.worker import Worker, listener
from Fairy.message_entity import EventMessage, CallMessage
from Fairy.type import EventType, EventStatus, CallType, MemoryType


class ShortTimeMemoryManager(Worker):
    def __init__(self, runtime):
        super().__init__(runtime, "ShortTimeMemoryManager", "ShortTimeMemoryManager")
        self.memory_list = {}
        self.current_memory = {
            MemoryType.Instruction: None,
            MemoryType.Plan: [],
            MemoryType.ScreenPerception: [],
            MemoryType.Action: [],
            MemoryType.ActionResult: [],
            MemoryType.KeyInfo: []
        } # 暂时只有一个短时记忆，暂未考虑多个短时记忆的情况

        self.memory_ready_event = {}
        self.allow_empty_list = [MemoryType.Action, MemoryType.ActionResult, MemoryType.KeyInfo]

    async def _get_memory(self, memory_type):
        memory = self.current_memory.get(memory_type)
        if memory_type not in self.allow_empty_list and (memory is None or memory == []):
            self.memory_ready_event[memory_type] = asyncio.Event()
            # 等待记忆被提供
            logger.debug(f"Waiting for memory {memory_type} to provide.")
            await self.memory_ready_event[memory_type].wait()
            self.memory_ready_event.pop(memory_type)
            # 重新获取记忆
            memory = self.current_memory.get(memory_type)
        return memory

    async def set_memory_ready(self, memory_type):
        if memory_type in self.memory_ready_event:
            # 通知等待记忆提供的任务
            self.memory_ready_event[memory_type].set()

    @listener(ListenerType.ON_CALLED, listen_filter=lambda message: message.call == CallType.Memory_GET)
    async def get_memory(self, message: CallMessage, message_context):
        memory = {}
        for memory_type in message.call_content:
            memory[memory_type] = await self._get_memory(memory_type)
        return memory

    @listener(ListenerType.ON_NOTIFIED, channel="app_channel",
              listen_filter=lambda message: message.event == EventType.Plan and message.status == EventStatus.CREATED)
    async def set_instruction(self, message: EventMessage, message_context):
        self.current_memory[MemoryType.Instruction] = message.event_content
        await self.set_memory_ready(MemoryType.Plan)

    @listener(ListenerType.ON_NOTIFIED, channel="app_channel",
              listen_filter=lambda message: message.event == EventType.ScreenPerception and message.status == EventStatus.DONE)
    async def set_screen_perception_memory(self, message: EventMessage, message_context):
        self.current_memory[MemoryType.ScreenPerception].append(message.event_content)
        await self.set_memory_ready(MemoryType.ScreenPerception)

    @listener(ListenerType.ON_NOTIFIED, channel="app_channel",
              listen_filter=lambda message: message.event == EventType.Plan and message.status == EventStatus.DONE)
    async def set_plan_memory(self, message: EventMessage, message_context):
        self.current_memory[MemoryType.Plan].append(message.event_content)
        await self.set_memory_ready(MemoryType.Plan)

    @listener(ListenerType.ON_NOTIFIED, channel="app_channel",
              listen_filter=lambda message: message.event == EventType.Reflection and message.status == EventStatus.DONE)
    async def set_action_result_memory(self, message: EventMessage, message_context):
        self.current_memory[MemoryType.ActionResult].append(message.event_content)
        await self.set_memory_ready(MemoryType.ActionResult)

    @listener(ListenerType.ON_NOTIFIED, channel="app_channel",
              listen_filter=lambda message: message.event == EventType.ActionExecution and message.status == EventStatus.DONE)
    async def set_action_memory(self, message: EventMessage, message_context):
        self.current_memory[MemoryType.Action].append(message.event_content)
        await self.set_memory_ready(MemoryType.Action)

    @listener(ListenerType.ON_NOTIFIED, channel="app_channel",
              listen_filter=lambda message: message.event == EventType.KeyInfoExtraction and message.status == EventStatus.DONE)
    async def set_key_info_memory(self, message: EventMessage, message_context):
        self.current_memory[MemoryType.KeyInfo].append(message.event_content)
        await self.set_memory_ready(MemoryType.KeyInfo)
