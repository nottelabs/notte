import base64
import io
import math
import tempfile
import textwrap
from collections import Counter
from pathlib import Path
from typing import Any, final

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, model_validator


def extract_frame_from_webp(
    frame_idx: int,
    input_path: str | Path,
) -> Image.Image:
    """
    Extract the last frame from a WebP image and save it as PNG.

    Args:
        input_path: Path to the input WebP file
        output_path: Optional path for output PNG file. If None, uses input name with .png extension

    Returns:
        Path to the output PNG file
    """
    input_path = Path(input_path)

    with Image.open(input_path) as img:
        # Check if image is animated
        if hasattr(img, "is_animated") and img.is_animated:  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
            # Get the number of frames
            frame_count = getattr(img, "n_frames", 1)

            if frame_idx < 0:
                frame_idx = frame_count + frame_idx

            # Seek to the last frame (frames are 0-indexed)
            img.seek(frame_idx)

        # Convert to RGB if necessary (WebP can have transparency)
        if img.mode in ("RGBA", "LA", "P"):
            # Create white background for transparent images
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

    return img


@final
class WebpReplay:
    """A class for handling WebP replay animations.

    This class provides functionality to work with WebP replay animations, including saving,
    extracting frames, and displaying the animation. It's particularly useful for handling
    browser session replays and screenshots.

    Args:
        replay: The WebP animation data as bytes.
    """

    def __init__(self, replay: bytes):
        self.replay = replay

    def save(self, output_file: str) -> None:
        """Save the WebP replay to a file.

        Args:
            output_file: Path where to save the WebP file. Must end with .webp extension.

        Raises:
            ValueError: If the output file doesn't have a .webp extension.
        """
        if not output_file.endswith(".webp"):
            raise ValueError("Output file must have a .webp extension.")
        with open(output_file, "wb") as f:
            _ = f.write(self.replay)

    def frame(self, frame_idx: int) -> Image.Image:
        """Extract a specific frame from the WebP animation.

        Args:
            frame_idx: Index of the frame to extract. Can be negative to count from the end.

        Returns:
            PIL.Image.Image: The extracted frame as a PIL Image object.
        """
        with tempfile.NamedTemporaryFile(suffix=".webp") as f:
            _ = f.write(self.replay)
            return extract_frame_from_webp(frame_idx, f.name)

    def save_frame(self, frame_idx: int, output_file: str | Path) -> None:
        """Save a specific frame from the WebP animation as a PNG file.

        Args:
            frame_idx: Index of the frame to save. Can be negative to count from the end.
            output_file: Path where to save the PNG file. The extension will be changed to .png if needed.
        """
        output_file = Path(output_file)
        output_file = output_file.with_suffix(".png")

        img = self.frame(frame_idx)
        img.save(output_file, "PNG")

    @staticmethod
    def in_notebook() -> bool:
        """Check if the code is running in a Jupyter notebook environment.

        Returns:
            bool: True if running in a notebook, False otherwise.
        """
        try:
            from IPython import get_ipython  # pyright: ignore[reportPrivateImportUsage]

            ipython = get_ipython()
            if ipython is None or "IPKernelApp" not in ipython.config:  # pragma: no cover
                return False
        except ImportError:
            return False
        except AttributeError:
            return False
        return True

    def display(self) -> Any | None:
        """Display the WebP replay in the current environment.

        If running in a Jupyter notebook, displays the animation inline.
        Otherwise, opens the animation in the default image viewer.

        Returns:
            IPython.display.Image | None: The displayed image object if in a notebook, None otherwise.
        """
        if WebpReplay.in_notebook():
            from IPython.display import Image as IPythonImage

            return IPythonImage(self.replay, format="webp")
        else:
            image = Image.open(io.BytesIO(self.replay))
            image.show()


class ScreenshotReplay(BaseModel):
    class Config:
        frozen: bool = True

    b64_screenshots: list[str]
    _pillow_images: list[Image.Image] = []

    @model_validator(mode="after")
    def process_images(self) -> "ScreenshotReplay":
        """Process base64 screenshots into standardized PIL images after model initialization."""
        if not self.b64_screenshots:
            self._pillow_images = []
            return self

        # Convert base64 to pillow images
        images = [self.base64_to_pillow_image(screen) for screen in self.b64_screenshots]

        if not images:
            self._pillow_images = []
            return self

        sizes = [img.size for img in images if img.size[0] > 1 and img.size[1] > 1]
        most_common_size = Counter(sizes).most_common(1)[0][0] if sizes else images[0].size

        # Standardize all images to the most common size
        standardized_images: list[Image.Image] = []
        for img in images:
            if img.size != most_common_size:
                img = img.resize(most_common_size)
            standardized_images.append(img)

        self._pillow_images = standardized_images
        return self

    @property
    def pillow_images(self) -> list[Image.Image]:
        return self._pillow_images

    @classmethod
    def from_base64(cls, screenshots: list[str]):
        return cls(b64_screenshots=screenshots)

    def to_bytes(self) -> list[bytes]:
        return [base64.b64decode(screen) for screen in self.b64_screenshots]

    @classmethod
    def from_bytes(cls, screenshots: list[bytes]):
        as_base64 = [base64.b64encode(screen).decode() for screen in screenshots]
        return cls(b64_screenshots=as_base64)

    @staticmethod
    def base64_to_pillow_image(screenshot: str) -> Image.Image:
        image_data = base64.b64decode(screenshot)
        return Image.open(io.BytesIO(image_data))

    def build_webp(
        self,
        scale_factor: float = 0.7,
        quality: int = 25,
        frametime_in_ms: int = 1000,
        start_text: str = "Start",
        ignore_incorrect_size: bool = False,
        step_text: list[str] | None = None,
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

            (width, height) = (int(math.ceil(prev_size[0] * scale_factor)), int(math.ceil(prev_size[1] * scale_factor)))

            resized_screenshots.append(im.resize((width, height)))

        width, height = resized_screenshots[0].size

        # fonts
        min_len = max(min(width, height), 25)
        small_font = ImageFont.load_default(size=min_len // 25)
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

        if step_text is not None and len(step_text) != len(resized_screenshots):
            raise ValueError(
                f"number of step text should match number of screenshots but got {len(step_text)=} and {len(resized_screenshots)=}"
            )

        resized_screenshots.insert(0, start_image)
        if step_text is not None:
            step_text.insert(0, "")

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

            if step_text is not None:
                text = step_text[i]
                draw.text(
                    (width // 2, 4 * height // 5),
                    "\n".join(textwrap.wrap(text, width=30)),
                    fill="white",
                    anchor="mm",
                    font=small_font,
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

    def get(self, **kwargs: dict[Any, Any]) -> WebpReplay:
        return WebpReplay(self.build_webp(**kwargs))  # pyright: ignore [reportArgumentType]
