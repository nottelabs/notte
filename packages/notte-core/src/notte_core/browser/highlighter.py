import io
from typing import ClassVar

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
        return self.x + self.iframe_offset_x

    @property
    def absolute_y(self) -> float:
        return self.y + self.iframe_offset_y

    def with_id(self, id: str) -> "BoundingBox":
        self.notte_id = id
        return self


class ScreenshotHighlighter:
    """Handles element highlighting using Python image processing"""

    colors: ClassVar[dict[str, str]] = {
        "L": "#0B9D68",
        "B": "#2B2BF7",
        "I": "#F68B30",
        "F": "#FF69B4",
        "O": "#4682B4",
        "M": "#F0554D",
    }
    scale_increment: ClassVar[float] = 0.25

    @staticmethod
    def forward(screenshot: bytes, bounding_boxes: list[BoundingBox]) -> bytes:
        """Add highlights to screenshot based on bounding boxes"""
        image = Image.open(io.BytesIO(screenshot))
        draw = ImageDraw.Draw(image)
        img_width, img_height = image.size
        placed_labels: list[tuple[float, float, float, float]] = []  # (x1, y1, x2, y2) for each label

        for bbox in bounding_boxes:
            if bbox.notte_id is None:
                raise ValueError("Bounding box must have a valid notte_id")
            color_key = bbox.notte_id[0]
            color = ScreenshotHighlighter.colors.get(color_key, "#808080")
            ScreenshotHighlighter._draw_highlight(
                draw, bbox, color, label=bbox.notte_id, placed_labels=placed_labels, img_size=(img_width, img_height)
            )

        # Convert back to bytes
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    @staticmethod
    def _draw_highlight(draw: ImageDraw.ImageDraw, bbox: BoundingBox, color: str, label: str):
        """Draw a single highlight rectangle and label, scaling from DOM viewport to screenshot size."""
        # Get the image size from the draw object
        img_width, img_height = draw.im.size  # type: ignore
        # Compute scale factors and round to nearest scale_increment=0.25
        scale_x = (
            round(float(img_width / bbox.viewport_width) / ScreenshotHighlighter.scale_increment)  # type: ignore
            * ScreenshotHighlighter.scale_increment
        )
        scale_y = (
            round(float(img_height / bbox.viewport_height) / ScreenshotHighlighter.scale_increment)  # type: ignore
            * ScreenshotHighlighter.scale_increment
        )

        # Transform DOM coordinates to image coordinates
        x1 = (bbox.absolute_x) * scale_x
        y1 = (bbox.absolute_y) * scale_y
        x2 = (bbox.absolute_x + bbox.width) * scale_x
        y2 = (bbox.absolute_y + bbox.height) * scale_y
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
        ScreenshotHighlighter._draw_label_scaled(
            draw, x1, y1, x2, y2, color, label, placed_labels, img_width, img_height
        )

    @staticmethod
    def _rects_overlap(r1: tuple[float, float, float, float], r2: tuple[float, float, float, float]) -> bool:
        # r = (x1, y1, x2, y2)
        return not (r1[2] <= r2[0] or r1[0] >= r2[2] or r1[3] <= r2[1] or r1[1] >= r2[3])

    @staticmethod
    def _draw_label_scaled(
        draw: ImageDraw.ImageDraw,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: str,
        label: str,
        placed_labels: list[tuple[float, float, float, float]],
        img_width: int,
        img_height: int,
    ):
        # Always use the default font, but try to set size to 14 if possible
        try:
            font = ImageFont.load_default(size=14)
        except Exception:
            font = ImageFont.load_default()
        # Use getbbox for accurate text size (Pillow >=8.0.0), fallback to textsize
        try:
            bbox = font.getbbox(label)
            text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except AttributeError:
            # Fallback: estimate size (very rough)
            text_w, text_h = 8 * len(label), 16
        pad_x, pad_y = 4, 4
        label_width = text_w + 2 * pad_x
        label_height = text_h + 2 * pad_y

        # Candidate positions: (label_x, label_y)
        candidates: list[tuple[float, float]] = []
        # Above
        candidates.append((x1, y1 - label_height - 2))
        # Right
        candidates.append((x2 + 2, y1))
        # Below
        candidates.append((x1, y2 + 2))
        # Left
        candidates.append((x1 - label_width - 2, y1))
        # Inside top-right
        candidates.append((x2 - label_width - 2, y1 + 2))

        chosen_rect = None
        for label_x, label_y in candidates:
            # Clamp to image bounds
            lx = max(0, min(label_x, img_width - label_width))
            ly = max(0, min(label_y, img_height - label_height))
            rect = (lx, ly, lx + label_width, ly + label_height)
            # Check overlap
            if any(ScreenshotHighlighter._rects_overlap(rect, r) for r in placed_labels):
                continue
            # Check if fully within image
            if rect[0] < 0 or rect[1] < 0 or rect[2] > img_width or rect[3] > img_height:
                continue
            chosen_rect = rect
            break
        if chosen_rect is None:
            # As last resort, clamp inside image, even if overlapping
            label_x, label_y = (
                max(0, min(x2 - label_width - 2, img_width - label_width)),
                max(0, min(y1 + 2, img_height - label_height)),
            )
            chosen_rect = (label_x, label_y, label_x + label_width, label_y + label_height)
        # Draw label background
        draw.rectangle(chosen_rect, fill=color)
        # Center text
        # Use anchor="mm" (middle middle) for automatic centering
        text_x = (chosen_rect[0] + chosen_rect[2]) / 2
        text_y = (chosen_rect[1] + chosen_rect[3]) / 2
        draw.text((text_x, text_y), label, fill="white", font=font, anchor="mm")
        placed_labels.append(chosen_rect)
