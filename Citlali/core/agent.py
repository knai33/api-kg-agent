import functools
from typing import List

from loguru import logger

from .worker import Worker
from ..models.entity import ChatMessage
from ..utils.image import Image


class Agent(Worker):
    def __init__(self, runtime, name, model_client, system_messages, desc=None):
        super().__init__(runtime, name ,desc)
        self._model_client = model_client
        self._system_messages = system_messages

    async def request_llm(self, content: str, images: List[Image] = []):
        user_message = ChatMessage(content=[content]+images, type="UserMessage", source="user")
        response = await self._model_client.create(
            self._system_messages + [user_message]
        )
        responses = self.parse_response(response.content)
        if isinstance(responses, tuple):
            logger.info("LLM Response: ")
            for r in responses:
                logger.info(str(r))
        else:
            logger.info("LLM Response: " + str(responses))
        return responses

    def parse_response(self, content: str):
        ...