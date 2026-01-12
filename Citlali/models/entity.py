from typing import Union, List, Literal, Optional

from Citlali.utils.image import Image

class ChatMessage:
    def __init__(self, content, type, source = None):
        self.content: Union[str, List[Union[str, Image]]] = content
        if type == "UserMessage":
            self.source: str = source
        self.type: Literal["UserMessage", "SystemMessage"] = type

    def convert(self):
        ...

class ResultMessage:
    def __init__(self, finish_reason, content, usage, thought=None):
        self.finish_reason: str = finish_reason
        self.content: str = content
        self.usage: ModelUsage = usage
        self.thought: Optional[str] = thought

    def __str__(self):
        return self.content

class ModelUsage:
    def __init__(self, prompt_tokens, completion_tokens):
        self.prompt_tokens: int = prompt_tokens
        self.completion_tokens: int = completion_tokens