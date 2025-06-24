import io

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel


class BoundingBox(BaseModel):
    """Represents element bounding box coordinates"""

    x: float
    y: float
    width: float
    height: float
    scroll_x: float
    scroll_y: float
    iframe_offset_x: float = 0
    iframe_offset_y: float = 0
    viewport_width: float
    viewport_height: float
    notte_id: str | None = None

    @property
    def absolute_x(self) -> float:
        return self.x + self.scroll_x + self.iframe_offset_x

    @property
    def absolute_y(self) -> float:
        return self.y + self.scroll_y + self.iframe_offset_y

    def with_id(self, id: str) -> "BoundingBox":
        self.notte_id = id
        return self


class BoundingBoxWithId(BoundingBox):
    id: str


class ScreenshotHighlighter:
    """Handles element highlighting using Python image processing"""

    def __init__(self):
        self.colors: dict[str, str] = {
            "L": "#00FF00",
            "B": "#0000FF",
            "I": "#FFA500",
            "F": "#FF69B4",
            "O": "#4682B4",
            "M": "#FF0000",
        }

    def highlight_elements(self, screenshot: bytes, bounding_boxes: list[BoundingBoxWithId]) -> bytes:
        """Add highlights to screenshot based on bounding boxes"""
        image = Image.open(io.BytesIO(screenshot))
        draw = ImageDraw.Draw(image)

        for bbox in bounding_boxes:
            if bbox.notte_id is None:
                raise ValueError("Bounding box must have a valid notte_id")
            color_key = bbox.notte_id[0]  # if bbox.notte_id else random.choice(list(self.colors.keys()))
            color = self.colors[color_key]
            self._draw_highlight(draw, bbox, color, label=bbox.notte_id)

        # Convert back to bytes
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    def _draw_highlight(self, draw: ImageDraw.ImageDraw, bbox: BoundingBox, color: str, label: str):
        """Draw a single highlight rectangle and label, scaling from DOM viewport to screenshot size."""
        # Get the image size from the draw object
        # PIL.Image.Image
        image = draw.im  # type: ignore
        img_width, img_height = image.size  # type: ignore
        # Compute scale factors
        scale_x = float(img_width / bbox.viewport_width)  # type: ignore
        scale_y = float(img_height / bbox.viewport_height)  # type: ignore

        # Transform DOM coordinates to image coordinates
        x1 = (bbox.absolute_x) * scale_x
        y1 = (bbox.absolute_y) * scale_y
        x2 = (bbox.absolute_x + bbox.width) * scale_x
        y2 = (bbox.absolute_y + bbox.height) * scale_y

        # Draw border rectangle
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
        # Draw label (scaled as well)
        self._draw_label_scaled(draw, x1, y1, x2, y2, color, label)

    def _draw_label_scaled(
        self, draw: ImageDraw.ImageDraw, x1: float, y1: float, x2: float, y2: float, color: str, label: str
    ):
        """Draw the index label, scaled to the image coordinates."""
        label_width = 20
        label_height = 16
        # Default position (top-right corner inside the box)
        label_x = x2 - label_width - 2
        label_y = y1 + 2
        # Adjust if box is too small
        if (x2 - x1) < label_width + 4 or (y2 - y1) < label_height + 4:
            label_x = x2 - label_width
            label_y = y1 - label_height - 2
        # Draw label background
        draw.rectangle([label_x, label_y, label_x + label_width, label_y + label_height], fill=color)
        # Draw text
        try:
            font = ImageFont.load_default(size=10)
            draw.text((label_x + 2, label_y + 2), label, fill="white", font=font)
        except Exception:
            draw.text((label_x + 2, label_y + 2), label, fill="white")
