import io

from PIL import Image


def image_from_bytes(image_bytes: bytes) -> Image.Image | None:
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Image.UnidentifiedImageError:
        return None
    return image
