import io
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

from notte_core.profiling import profiler


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


class LabelPosition(Enum):
    """Enumeration of possible label positions relative to the element"""

    ABOVE_LEFT = 0
    ABOVE_CENTER = 1
    ABOVE_RIGHT = 2
    RIGHT_TOP = 3
    RIGHT_CENTER = 4
    RIGHT_BOTTOM = 5
    BELOW_LEFT = 6
    BELOW_CENTER = 7
    BELOW_RIGHT = 8
    LEFT_TOP = 9
    LEFT_CENTER = 10
    LEFT_BOTTOM = 11
    INSIDE_TOP_RIGHT = 12
    INSIDE_TOP_LEFT = 13
    INSIDE_BOTTOM_RIGHT = 14
    INSIDE_BOTTOM_LEFT = 15


@dataclass
class Rectangle:
    """Represents a rectangle with x1, y1, x2, y2 coordinates"""

    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2

    def overlaps(self, other: "Rectangle") -> bool:
        """Check if this rectangle overlaps with another"""
        return not (self.x2 <= other.x1 or self.x1 >= other.x2 or self.y2 <= other.y1 or self.y1 >= other.y2)


@dataclass
class LabelConfig:
    """Configuration for label appearance and behavior"""

    font_size: int = 14
    padding_x: int = 4
    padding_y: int = 4
    tail_size_ratio: float = 0.6
    tail_length_ratio: float = 0.4
    inside_tail_size_ratio: float = 0.5
    inside_tail_length_ratio: float = 0.3
    color_uniformity_threshold: float = 0.9
    color_tolerance: int = 30
    label_opacity: int = 204  # 80% opacity
    outline_opacity: int = 255  # 100% opacity
    # Performance optimization flags
    fast_mode: bool = True  # Skip expensive color analysis
    max_candidates: int = 8  # Limit candidate positions to evaluate
    skip_color_analysis: bool = True  # Skip color uniformity checks


class ColorAnalyzer:
    """Handles color analysis for label placement optimization"""

    @staticmethod
    def is_area_uniform_color(image: Image.Image, rect: Rectangle, config: LabelConfig) -> bool:
        """
        Check if an area is mostly uniform color (indicating no content).

        Args:
            image: PIL Image to analyze
            rect: Rectangle area to analyze
            config: Label configuration

        Returns:
            True if area is mostly uniform color, False otherwise
        """
        # Clamp coordinates to image bounds
        x1 = max(0, min(int(rect.x1), image.width - 1))
        y1 = max(0, min(int(rect.y1), image.height - 1))
        x2 = max(0, min(int(rect.x2), image.width))
        y2 = max(0, min(int(rect.y2), image.height))

        if x2 <= x1 or y2 <= y1:
            return False

        # Extract the region
        region = image.crop((x1, y1, x2, y2))

        # Convert to RGB if needed
        if region.mode != "RGB":
            region = region.convert("RGB")

        # Get pixel data
        pixels: list[list[int]] = list(region.getdata())  # pyright: ignore [reportUnknownArgumentType, reportUnknownMemberType]
        if not pixels:
            return True

        # Calculate average color
        total_r = sum(p[0] for p in pixels)
        total_g = sum(p[1] for p in pixels)
        total_b = sum(p[2] for p in pixels)
        num_pixels = len(pixels)

        avg_r = total_r / num_pixels
        avg_g = total_g / num_pixels
        avg_b = total_b / num_pixels

        # Count pixels that are similar to average (within tolerance)
        similar_pixels = 0

        for r, g, b in pixels:
            # Calculate color distance
            distance = ((r - avg_r) ** 2 + (g - avg_g) ** 2 + (b - avg_b) ** 2) ** 0.5
            if distance <= config.color_tolerance:
                similar_pixels += 1

        uniformity = similar_pixels / num_pixels
        return uniformity >= config.color_uniformity_threshold


class CoordinateTransformer:
    """Handles coordinate transformation from DOM to image coordinates"""

    def __init__(self, img_width: int, img_height: int, viewport_width: float, viewport_height: float):
        self.img_width: int = img_width
        self.img_height: int = img_height
        self.viewport_width: float = viewport_width
        self.viewport_height: float = viewport_height
        self.scale_increment: float = 0.25

    def transform_bbox(self, bbox: BoundingBox) -> Rectangle:
        """Transform DOM coordinates to image coordinates"""
        # Compute scale factors and round to nearest scale_increment
        # scale_x = round(float(self.img_width / self.viewport_width) / self.scale_increment) * self.scale_increment
        # scale_y = round(float(self.img_height / self.viewport_height) / self.scale_increment) * self.scale_increment
        #
        # # Transform DOM coordinates to image coordinates
        # x1 = bbox.absolute_x * scale_x
        # y1 = bbox.absolute_y * scale_y
        # x2 = (bbox.absolute_x + bbox.width) * scale_x
        # y2 = (bbox.absolute_y + bbox.height) * scale_y

        # return Rectangle(x1, y1, x2, y2)
        return Rectangle(bbox.absolute_x, bbox.absolute_y, bbox.absolute_x + bbox.width, bbox.absolute_y + bbox.height)


class LabelPlacementOptimizer:
    """Handles label placement optimization"""

    def __init__(self, img_width: int, img_height: int, config: LabelConfig):
        self.img_width: int = img_width
        self.img_height: int = img_height
        self.config: LabelConfig = config
        self.color_analyzer: ColorAnalyzer = ColorAnalyzer()

    def find_best_position(
        self, element_rect: Rectangle, label_rect: Rectangle, placed_labels: list[Rectangle], image: Image.Image
    ) -> tuple[Rectangle, LabelPosition]:
        """Find the best position for a label"""
        candidates = self._generate_candidates(element_rect, label_rect)

        best_rect = None
        best_score = -1
        best_position = LabelPosition.INSIDE_TOP_RIGHT  # Default

        candidate_count = 0
        for position, (label_x, label_y) in candidates.items():
            # Limit number of candidates evaluated in fast mode
            if self.config.fast_mode and candidate_count >= self.config.max_candidates:
                break

            # Clamp to image bounds
            lx = max(0, min(label_x, self.img_width - label_rect.width))
            ly = max(0, min(label_y, self.img_height - label_rect.height))
            rect = Rectangle(lx, ly, lx + label_rect.width, ly + label_rect.height)

            # Check if fully within image
            if not self._is_within_bounds(rect):
                continue

            # Check overlap with existing labels
            if any(rect.overlaps(existing) for existing in placed_labels):
                continue

            # Score this position
            score = self._calculate_position_score(rect, element_rect, image)

            if score > best_score:
                best_score = score
                best_rect = rect
                best_position = position

                # Early termination in fast mode if we find a good enough position
                if self.config.fast_mode and score >= 8:  # Good enough score
                    break

            candidate_count += 1

        # Fallback: use inside top-right if no good position found
        if best_rect is None:
            label_x = max(0, min(element_rect.x2 - label_rect.width - 2, self.img_width - label_rect.width))
            label_y = max(0, min(element_rect.y1 + 2, self.img_height - label_rect.height))
            best_rect = Rectangle(label_x, label_y, label_x + label_rect.width, label_y + label_rect.height)
            best_position = LabelPosition.INSIDE_TOP_RIGHT

        return best_rect, best_position

    def _generate_candidates(
        self, element_rect: Rectangle, label_rect: Rectangle
    ) -> dict[LabelPosition, tuple[float, float]]:
        """Generate candidate positions for label placement"""
        candidates: dict[LabelPosition, tuple[float, float]] = {}

        # In fast mode, only generate a subset of candidates
        if self.config.fast_mode:
            # Prioritize inside positions and a few key outside positions
            candidates[LabelPosition.INSIDE_TOP_RIGHT] = (element_rect.x2 - label_rect.width - 2, element_rect.y1 + 2)
            candidates[LabelPosition.INSIDE_TOP_LEFT] = (element_rect.x1 + 2, element_rect.y1 + 2)
            candidates[LabelPosition.ABOVE_CENTER] = (
                element_rect.x1 + (element_rect.width - label_rect.width) / 2,
                element_rect.y1 - label_rect.height - 8,
            )
            candidates[LabelPosition.RIGHT_TOP] = (element_rect.x2 + 8, element_rect.y1)
            candidates[LabelPosition.BELOW_CENTER] = (
                element_rect.x1 + (element_rect.width - label_rect.width) / 2,
                element_rect.y2 + 8,
            )
            candidates[LabelPosition.LEFT_TOP] = (element_rect.x1 - label_rect.width - 8, element_rect.y1)
            candidates[LabelPosition.INSIDE_BOTTOM_RIGHT] = (
                element_rect.x2 - label_rect.width - 2,
                element_rect.y2 - label_rect.height - 2,
            )
            candidates[LabelPosition.INSIDE_BOTTOM_LEFT] = (
                element_rect.x1 + 2,
                element_rect.y2 - label_rect.height - 2,
            )
        else:
            # Generate all candidates (original behavior)
            # Above positions
            candidates[LabelPosition.ABOVE_LEFT] = (element_rect.x1, element_rect.y1 - label_rect.height - 8)
            candidates[LabelPosition.ABOVE_CENTER] = (
                element_rect.x1 + (element_rect.width - label_rect.width) / 2,
                element_rect.y1 - label_rect.height - 8,
            )
            candidates[LabelPosition.ABOVE_RIGHT] = (
                element_rect.x2 - label_rect.width,
                element_rect.y1 - label_rect.height - 8,
            )

            # Right positions
            candidates[LabelPosition.RIGHT_TOP] = (element_rect.x2 + 8, element_rect.y1)
            candidates[LabelPosition.RIGHT_CENTER] = (
                element_rect.x2 + 8,
                element_rect.y1 + (element_rect.height - label_rect.height) / 2,
            )
            candidates[LabelPosition.RIGHT_BOTTOM] = (element_rect.x2 + 8, element_rect.y2 - label_rect.height)

            # Below positions
            candidates[LabelPosition.BELOW_LEFT] = (element_rect.x1, element_rect.y2 + 8)
            candidates[LabelPosition.BELOW_CENTER] = (
                element_rect.x1 + (element_rect.width - label_rect.width) / 2,
                element_rect.y2 + 8,
            )
            candidates[LabelPosition.BELOW_RIGHT] = (element_rect.x2 - label_rect.width, element_rect.y2 + 8)

            # Left positions
            candidates[LabelPosition.LEFT_TOP] = (element_rect.x1 - label_rect.width - 8, element_rect.y1)
            candidates[LabelPosition.LEFT_CENTER] = (
                element_rect.x1 - label_rect.width - 8,
                element_rect.y1 + (element_rect.height - label_rect.height) / 2,
            )
            candidates[LabelPosition.LEFT_BOTTOM] = (
                element_rect.x1 - label_rect.width - 8,
                element_rect.y2 - label_rect.height,
            )

            # Inside positions
            candidates[LabelPosition.INSIDE_TOP_RIGHT] = (element_rect.x2 - label_rect.width - 2, element_rect.y1 + 2)
            candidates[LabelPosition.INSIDE_TOP_LEFT] = (element_rect.x1 + 2, element_rect.y1 + 2)
            candidates[LabelPosition.INSIDE_BOTTOM_RIGHT] = (
                element_rect.x2 - label_rect.width - 2,
                element_rect.y2 - label_rect.height - 2,
            )
            candidates[LabelPosition.INSIDE_BOTTOM_LEFT] = (
                element_rect.x1 + 2,
                element_rect.y2 - label_rect.height - 2,
            )

        return candidates

    def _is_within_bounds(self, rect: Rectangle) -> bool:
        """Check if rectangle is within image bounds"""
        return rect.x1 >= 0 and rect.y1 >= 0 and rect.x2 <= self.img_width and rect.y2 <= self.img_height

    def _calculate_position_score(self, label_rect: Rectangle, element_rect: Rectangle, image: Image.Image) -> int:
        """Calculate score for a label position"""
        score = 0

        # Skip expensive color analysis in fast mode
        if not self.config.skip_color_analysis:
            # High score for uniform areas
            if self.color_analyzer.is_area_uniform_color(image, label_rect, self.config):
                score += 10

        # Bonus for positions that don't overlap with the highlighted element
        if not label_rect.overlaps(element_rect):
            score += 5

        # Bonus for positions outside the element
        if (
            label_rect.x1 < element_rect.x1
            or label_rect.x2 > element_rect.x2
            or label_rect.y1 < element_rect.y1
            or label_rect.y2 > element_rect.y2
        ):
            score += 3

        # In fast mode, prioritize inside positions (they're usually safe)
        if self.config.fast_mode:
            if (
                label_rect.x1 >= element_rect.x1
                and label_rect.x2 <= element_rect.x2
                and label_rect.y1 >= element_rect.y1
                and label_rect.y2 <= element_rect.y2
            ):
                score += 8  # High priority for inside positions

        return score


class ArrowLabelRenderer:
    """Handles rendering of arrow-shaped labels"""

    def __init__(self, config: LabelConfig):
        self.config: LabelConfig = config

    def draw_arrow_label(
        self,
        draw: ImageDraw.ImageDraw,
        label_rect: Rectangle,
        color: tuple[int, int, int, int],
        position: LabelPosition,
        element_rect: Rectangle,
    ):
        """Draw a chat bubble style label with a small triangle tail pointing to the element"""
        # Draw the main label box
        draw.rectangle([label_rect.x1, label_rect.y1, label_rect.x2, label_rect.y2], fill=color)

        # Draw the tail based on position
        if position in [LabelPosition.ABOVE_LEFT, LabelPosition.ABOVE_CENTER, LabelPosition.ABOVE_RIGHT]:
            self._draw_tail_down(draw, label_rect, color, element_rect)
        elif position in [LabelPosition.RIGHT_TOP, LabelPosition.RIGHT_CENTER, LabelPosition.RIGHT_BOTTOM]:
            self._draw_tail_left(draw, label_rect, color, element_rect)
        elif position in [LabelPosition.BELOW_LEFT, LabelPosition.BELOW_CENTER, LabelPosition.BELOW_RIGHT]:
            self._draw_tail_up(draw, label_rect, color, element_rect)
        elif position in [LabelPosition.LEFT_TOP, LabelPosition.LEFT_CENTER, LabelPosition.LEFT_BOTTOM]:
            self._draw_tail_right(draw, label_rect, color, element_rect)
        else:  # Inside positions
            self._draw_inside_tail(draw, label_rect, color, element_rect)

    def _draw_tail_down(
        self,
        draw: ImageDraw.ImageDraw,
        label_rect: Rectangle,
        color: tuple[int, int, int, int],
        element_rect: Rectangle,
    ):
        """Draw tail pointing down from label to element"""
        tail_size = min(label_rect.width, label_rect.height) * self.config.tail_size_ratio
        tail_length = min(label_rect.width, label_rect.height) * self.config.tail_length_ratio

        # Point the tail toward the element's center, but clamp to label bounds
        element_center_x = element_rect.center_x
        tail_x = max(label_rect.x1 + tail_size / 2, min(label_rect.x2 - tail_size / 2, element_center_x))
        tail_y = label_rect.y2  # Bottom of label

        # Calculate distance to element and ensure tail reaches it
        distance_to_element = element_rect.y1 - tail_y
        actual_tail_length = max(tail_length, distance_to_element - 1)

        tail_points = [
            (tail_x - tail_size / 2, tail_y),  # Top left
            (tail_x + tail_size / 2, tail_y),  # Top right
            (tail_x, tail_y + actual_tail_length),  # Bottom tip
        ]

        self._draw_tail_with_outline(draw, tail_points, color)

    def _draw_tail_left(
        self,
        draw: ImageDraw.ImageDraw,
        label_rect: Rectangle,
        color: tuple[int, int, int, int],
        element_rect: Rectangle,
    ):
        """Draw tail pointing left from label to element"""
        tail_size = min(label_rect.width, label_rect.height) * self.config.tail_size_ratio
        tail_length = min(label_rect.width, label_rect.height) * self.config.tail_length_ratio

        element_center_y = element_rect.center_y
        tail_x = label_rect.x1  # Left of label
        tail_y = max(label_rect.y1 + tail_size / 2, min(label_rect.y2 - tail_size / 2, element_center_y))

        distance_to_element = tail_x - element_rect.x2
        actual_tail_length = max(tail_length, distance_to_element - 1)

        tail_points = [
            (tail_x, tail_y - tail_size / 2),  # Left top
            (tail_x, tail_y + tail_size / 2),  # Left bottom
            (tail_x - actual_tail_length, tail_y),  # Left tip
        ]

        self._draw_tail_with_outline(draw, tail_points, color)

    def _draw_tail_up(
        self,
        draw: ImageDraw.ImageDraw,
        label_rect: Rectangle,
        color: tuple[int, int, int, int],
        element_rect: Rectangle,
    ):
        """Draw tail pointing up from label to element"""
        tail_size = min(label_rect.width, label_rect.height) * self.config.tail_size_ratio
        tail_length = min(label_rect.width, label_rect.height) * self.config.tail_length_ratio

        element_center_x = element_rect.center_x
        tail_x = max(label_rect.x1 + tail_size / 2, min(label_rect.x2 - tail_size / 2, element_center_x))
        tail_y = label_rect.y1  # Top of label

        distance_to_element = tail_y - element_rect.y2
        actual_tail_length = max(tail_length, distance_to_element - 1)

        tail_points = [
            (tail_x - tail_size / 2, tail_y),  # Bottom left
            (tail_x + tail_size / 2, tail_y),  # Bottom right
            (tail_x, tail_y - actual_tail_length),  # Top tip
        ]

        self._draw_tail_with_outline(draw, tail_points, color)

    def _draw_tail_right(
        self,
        draw: ImageDraw.ImageDraw,
        label_rect: Rectangle,
        color: tuple[int, int, int, int],
        element_rect: Rectangle,
    ):
        """Draw tail pointing right from label to element"""
        tail_size = min(label_rect.width, label_rect.height) * self.config.tail_size_ratio
        tail_length = min(label_rect.width, label_rect.height) * self.config.tail_length_ratio

        element_center_y = element_rect.center_y
        tail_x = label_rect.x2  # Right of label
        tail_y = max(label_rect.y1 + tail_size / 2, min(label_rect.y2 - tail_size / 2, element_center_y))

        distance_to_element = element_rect.x1 - tail_x
        actual_tail_length = max(tail_length, distance_to_element - 1)

        tail_points = [
            (tail_x, tail_y - tail_size / 2),  # Right top
            (tail_x, tail_y + tail_size / 2),  # Right bottom
            (tail_x + actual_tail_length, tail_y),  # Right tip
        ]

        self._draw_tail_with_outline(draw, tail_points, color)

    def _draw_inside_tail(
        self,
        draw: ImageDraw.ImageDraw,
        label_rect: Rectangle,
        color: tuple[int, int, int, int],
        element_rect: Rectangle,
    ):
        """Draw smaller tail for inside positions pointing outward"""
        inside_tail_size = min(label_rect.width, label_rect.height) * self.config.inside_tail_size_ratio

        # Determine which corner of the element we're closest to
        center_x = label_rect.center_x
        center_y = label_rect.center_y
        element_center_x = element_rect.center_x
        element_center_y = element_rect.center_y

        if center_x < element_center_x and center_y < element_center_y:
            # Top-left - tail points down-right
            tail_x = label_rect.x2
            tail_y = label_rect.y2
            tail_points = [
                (tail_x - inside_tail_size, tail_y - inside_tail_size),  # Top-left
                (tail_x, tail_y - inside_tail_size),  # Top-right
                (tail_x, tail_y),  # Bottom-right
            ]
        elif center_x > element_center_x and center_y < element_center_y:
            # Top-right - tail points down-left
            tail_x = label_rect.x1
            tail_y = label_rect.y2
            tail_points = [
                (tail_x, tail_y - inside_tail_size),  # Top-right
                (tail_x + inside_tail_size, tail_y - inside_tail_size),  # Top-left
                (tail_x, tail_y),  # Bottom-left
            ]
        elif center_x > element_center_x and center_y > element_center_y:
            # Bottom-right - tail points up-left
            tail_x = label_rect.x1
            tail_y = label_rect.y1
            tail_points = [
                (tail_x + inside_tail_size, tail_y + inside_tail_size),  # Bottom-right
                (tail_x, tail_y + inside_tail_size),  # Bottom-left
                (tail_x, tail_y),  # Top-left
            ]
        else:  # Bottom-left - tail points up-right
            tail_x = label_rect.x2
            tail_y = label_rect.y1
            tail_points = [
                (tail_x, tail_y + inside_tail_size),  # Bottom-left
                (tail_x - inside_tail_size, tail_y + inside_tail_size),  # Bottom-right
                (tail_x, tail_y),  # Top-right
            ]

        self._draw_tail_with_outline(draw, tail_points, color)

    def _draw_tail_with_outline(
        self, draw: ImageDraw.ImageDraw, tail_points: list[tuple[float, float]], color: tuple[int, int, int, int]
    ):
        """Draw tail with white outline"""
        white_outline = (255, 255, 255, self.config.outline_opacity)
        draw.polygon(tail_points, fill=white_outline)
        draw.polygon(tail_points, fill=color)


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

    @profiler.profiled()
    @staticmethod
    def forward(screenshot: bytes, bounding_boxes: list[BoundingBox]) -> bytes:
        """Add highlights to screenshot based on bounding boxes"""
        image = Image.open(io.BytesIO(screenshot)).convert("RGB")
        draw = ImageDraw.Draw(image, "RGBA")  # Enable alpha channel for transparency
        img_width, img_height = image.size

        # Initialize components
        config = LabelConfig()
        transformer = CoordinateTransformer(
            img_width, img_height, bounding_boxes[0].viewport_width, bounding_boxes[0].viewport_height
        )
        placement_optimizer = LabelPlacementOptimizer(img_width, img_height, config)
        arrow_renderer = ArrowLabelRenderer(config)

        placed_labels: list[Rectangle] = []

        for i, bbox in enumerate(bounding_boxes):
            if bbox.notte_id is None:
                raise ValueError("Bounding box must have a valid notte_id")

            color_key = bbox.notte_id[0]
            color = ScreenshotHighlighter.colors.get(color_key, "#808080")

            ScreenshotHighlighter._draw_highlight(
                draw=draw,
                bbox=bbox,
                color=color,
                label=bbox.notte_id,
                placed_labels=placed_labels,
                image=image,
                transformer=transformer,
                placement_optimizer=placement_optimizer,
                arrow_renderer=arrow_renderer,
                config=config,
                bbox_index=i,
            )

        # Convert back to bytes
        output = io.BytesIO()
        image.save(output, format="JPEG")
        result = output.getvalue()

        return result

    @staticmethod
    def _draw_highlight(
        draw: ImageDraw.ImageDraw,
        bbox: BoundingBox,
        color: str,
        label: str,
        placed_labels: list[Rectangle],
        image: Image.Image,
        transformer: CoordinateTransformer,
        placement_optimizer: LabelPlacementOptimizer,
        arrow_renderer: ArrowLabelRenderer,
        config: LabelConfig,
        bbox_index: int,
    ):
        """Draw a single highlight rectangle and label"""
        # Transform coordinates
        element_rect = transformer.transform_bbox(bbox)

        # Draw semi-transparent rectangle
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        rgba_outline = (r, g, b, 160)
        rgba_fill = (r, g, b, 15)

        draw.rectangle(
            [element_rect.x1, element_rect.y1, element_rect.x2, element_rect.y2],
            outline=rgba_outline,
            fill=rgba_fill,
            width=2,
        )

        # Create and place label
        ScreenshotHighlighter._create_and_place_label(
            draw=draw,
            element_rect=element_rect,
            color=color,
            label=label,
            placed_labels=placed_labels,
            image=image,
            placement_optimizer=placement_optimizer,
            arrow_renderer=arrow_renderer,
            config=config,
            bbox_index=bbox_index,
        )

    @staticmethod
    def _create_and_place_label(
        draw: ImageDraw.ImageDraw,
        element_rect: Rectangle,
        color: str,
        label: str,
        placed_labels: list[Rectangle],
        image: Image.Image,
        placement_optimizer: LabelPlacementOptimizer,
        arrow_renderer: ArrowLabelRenderer,
        config: LabelConfig,
        bbox_index: int,  # pyright: ignore [reportUnusedParameter]
    ):
        """Create and place a label with optimal positioning"""
        # Create font and calculate label dimensions
        try:
            font = ImageFont.load_default(size=config.font_size)
        except Exception:
            font = ImageFont.load_default()

        # Calculate text dimensions
        try:
            bbox = font.getbbox(label)
            text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except AttributeError:
            # Fallback: estimate size
            text_w, text_h = 8 * len(label), 16

        label_width = text_w + 2 * config.padding_x
        label_height = text_h + 2 * config.padding_y
        label_rect = Rectangle(0, 0, label_width, label_height)

        # Find best position
        best_rect, best_position = placement_optimizer.find_best_position(
            element_rect, label_rect, placed_labels, image
        )

        # Convert hex color to RGBA
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        rgba_color = (r, g, b, config.label_opacity)

        # Draw arrow label
        arrow_renderer.draw_arrow_label(draw, best_rect, rgba_color, best_position, element_rect)

        # Draw text
        text_x = best_rect.center_x
        text_y = best_rect.center_y
        draw.text((text_x, text_y), label, fill="white", font=font, anchor="mm")

        placed_labels.append(best_rect)
