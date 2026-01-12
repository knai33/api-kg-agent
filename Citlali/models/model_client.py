import json

class ChatClient:

    def __init__(self, model_infos, **kwargs):
        self.model_infos = model_infos

        if "model" not in kwargs:
            raise ValueError("model is required for ChatClient")

        if "model_info" in kwargs:
            self.model_info = kwargs["model_info"]
        else:
            self.model_info = self._get_model_info(kwargs["model"])

    async def create(
            self,
            messages,
            extra_create_args = {},
    ):
        ...

    def _get_model_info(self, model_name):
        with open(self.model_infos, 'r') as file:
            # 读取JSON数据
            data = json.load(file)
            return data[model_name]