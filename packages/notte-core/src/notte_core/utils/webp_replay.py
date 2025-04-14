import base64
import io
import textwrap

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel


class ScreenshotReplay(BaseModel):
    class Config:
        frozen: bool = True

    b64_screenshots: list[str]

    @property
    def pillow_images(self) -> list[Image.Image]:
        return [ScreenshotReplay.base64_to_pillow_image(screen) for screen in self.b64_screenshots]

    @classmethod
    def from_base64(cls, screenshots: list[str]):
        return cls(b64_screenshots=screenshots)

    @classmethod
    def from_bytes(cls, screenshots: list[bytes]):
        as_base64 = [base64.b64encode(screen).decode() for screen in screenshots]
        return cls(b64_screenshots=as_base64)

    @staticmethod
    def base64_to_pillow_image(screenshot: str) -> Image.Image:
        image_data = base64.b64decode(screenshot)
        return Image.open(io.BytesIO(image_data))

    def summary_webp(
        self,
        scale_factor: float = 0.7,
        quality: int = 25,
        frametime_in_ms: int = 1000,
        start_text: str = "Start",
        ignore_incorrect_size: bool = False,
    ) -> bytes:
        if len(self.b64_screenshots) == 0:
            return b""

        # resize images with scale factor
        resized_screenshots: list[Image.Image] = []
        prev_size = None
        for im in self.pillow_images:
            if prev_size is None:
                prev_size = im.size
            else:
                # if next images are of incorrect size, either ignore or reshape them
                if prev_size != im.size and ignore_incorrect_size:
                    continue

            (width, height) = (int(prev_size[0] * scale_factor), int(prev_size[1] * scale_factor))
            resized_screenshots.append(im.resize((width, height)))

        width, height = resized_screenshots[0].size

        # fonts
        min_len = min(width, height)
        medium_font = ImageFont.load_default(size=min_len // 20)
        big_font = ImageFont.load_default(size=min_len // 15)

        # first frame with start
        start_image = Image.new("RGB", (width, height), color="white")
        draw = ImageDraw.Draw(start_image)
        draw.text(
            (width // 2, height // 2),
            "\n".join(textwrap.wrap(start_text, width=30)),
            fill="black",
            anchor="mm",
            font=medium_font,
        )
        resized_screenshots.insert(0, start_image)

        # Add frame numbers to each screenshot
        for i, img in enumerate(resized_screenshots):
            draw = ImageDraw.Draw(img)
            frame_text = f"{i}"
            draw.text(
                (width - 10, height - 10),
                frame_text,
                fill="white",
                anchor="rb",
                font=big_font,
                stroke_width=4,
                stroke_fill="black",
            )

        # Save as animated WebP to bytes buffer
        buffer = io.BytesIO()
        resized_screenshots[0].save(
            buffer,
            "WEBP",
            save_all=True,
            append_images=resized_screenshots[1:],
            duration=frametime_in_ms,
            quality=quality,
            loop=0,
        )
        _ = buffer.seek(0)
        return buffer.getvalue()
