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
