import base64
from io import BytesIO

from PIL import Image as PILImage

class Image:
    def __init__(self, image: PILImage.Image):
        self.image: PILImage.Image = image.convert("RGB")

    @classmethod
    def from_base64(cls, base64_str: str):
        return cls(PILImage.open(BytesIO(base64.b64decode(base64_str))))

    def to_base64(self):
        buffered = BytesIO()
        self.image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

    def to_data_uri(self):
        base64_image = self.to_base64()
        image_data = base64.b64decode(base64_image)
        if image_data.startswith(b"\xff\xd8\xff"):
            mime_type = "image/jpeg"
        elif image_data.startswith(b"\x89PNG\r\n\x1a\n"):
            mime_type = "image/png"
        elif image_data.startswith(b"GIF87a") or image_data.startswith(b"GIF89a"):
            mime_type = "image/gif"
        elif image_data.startswith(b"RIFF") and image_data[8:12] == b"WEBP":
            mime_type = "image/webp"
        else:
            mime_type = "image/jpeg"
        data_uri = f"data:{mime_type};base64,{base64_image}"
        return data_uri