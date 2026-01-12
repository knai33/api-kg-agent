import asyncio
import inspect
import os
from typing import List, Sequence, Mapping, Any, cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam, \
    ChatCompletionContentPartImageParam, ChatCompletionContentPartTextParam
from openai.types.chat.chat_completion_content_part_image_param import ImageURL

from ..entity import ChatMessage, ModelUsage, ResultMessage
from ..model_client import ChatClient
from ...utils.image import Image


class OpenAIChatMessage(ChatMessage):
    def convert(self):
        match self.type:
            case "SystemMessage":
                return ChatCompletionSystemMessageParam(
                    content=self.content,
                    role="system",
                )
            case "UserMessage":
                if isinstance(self.content, str):
                    content = f"{self.source} said:\n" + self.content
                elif isinstance(self.content, List):
                    content = []
                    for content_item in self.content:
                        if isinstance(content_item, str):
                            content.append(
                                ChatCompletionContentPartTextParam(
                                    text=content_item,
                                    type="text",
                                )
                            )
                        elif isinstance(content_item, Image):
                            content.append(
                                ChatCompletionContentPartImageParam(
                                    image_url=ImageURL(
                                        url=content_item.to_data_uri(),
                                        detail="auto"
                                    ),
                                    type="image_url"
                                )
                            )
                else:
                    raise ValueError("Unsupported content type")
                return ChatCompletionUserMessageParam(
                    content=content,
                    role="user",
                    name=self.source,
                )


class OpenAIChatClient(ChatClient):

    def __init__(self, create_args):
        super().__init__(os.path.dirname(__file__)+"/model_info.json", **create_args)
        self._client = self._init_client(create_args)
        self._create_args = create_args

    @staticmethod
    def _init_client(create_args):
        openai_init_kwargs = set(inspect.getfullargspec(AsyncOpenAI.__init__).kwonlyargs)
        openai_config = {k: v for k, v in create_args.items() if k in openai_init_kwargs}
        return AsyncOpenAI(**openai_config)

    async def create(
            self,
            messages: Sequence[ChatMessage],
            json_output: bool = False,
            extra_create_args: Mapping[str, Any] = {},
    ):
        create_args = self._create_args.copy()
        create_args.update(extra_create_args)


        # 检查图像支持
        if self.model_info["vision"] is False:
            for message in messages:
                if isinstance(message.content, list) and any(isinstance(x, Image) for x in message.content):
                    raise ValueError("Model does not support vision but image was provided")

        # 检查JSON输出支持，并设置response_format
        if json_output and self.model_info["json_output"] is False:
                raise ValueError("Model does not support JSON output.")
        else:
            create_args["response_format"] = {"type": "json_object"} if json_output else {"type": "text"}

        # 转换消息
        messages = [OpenAIChatMessage.convert(message) for message in messages]

        # 创建对话
        future = asyncio.ensure_future(
            self._client.chat.completions.create(
                messages=messages,
                stream=False,
                **create_args)
        )

        result = await future

        # 获取Token用量信息
        usage = ModelUsage(
            prompt_tokens=result.usage.prompt_tokens if result.usage is not None else 0,
            completion_tokens=(result.usage.completion_tokens if result.usage is not None else 0),
        )

        # 构建ResultMessage响应
        choice = result.choices[0]
        response = ResultMessage(
            finish_reason = choice.finish_reason,
            content = choice.message.content or "",
            usage=usage,
        )

        return response


