import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from notte.actions.space import ActionSpace
from notte.browser.snapshot import BrowserSnapshot, clean_url
from notte.utils import image


@dataclass
class Observation:
    title: str
    url: str
    timestamp: dt.datetime = field(default_factory=dt.datetime.now)
    screenshot: bytes | None = None
    _space: ActionSpace | None = None
    data: str = ""

    @property
    def clean_url(self) -> str:
        return clean_url(self.url)

    @property
    def space(self) -> ActionSpace:
        if self._space is None:
            raise ValueError("Space is not available for this observation")
        return self._space

    @space.setter
    def space(self, space: ActionSpace) -> None:
        self._space = space

    def has_space(self) -> bool:
        return self._space is not None

    def has_data(self) -> bool:
        return self.data != ""

    def display_screenshot(self) -> Image.Image | None:
        if self.screenshot is None:
            return None
        return image.image_from_bytes(self.screenshot)

    @staticmethod
    def from_json(json: dict[str, Any]) -> "Observation":
        url: str | None = json.get("url", None)
        if not isinstance(url, str):
            raise ValueError("url must be a string")
        title: str | None = json.get("title", None)
        if not isinstance(title, str):
            raise ValueError("title must be a string")
        timestamp: dt.datetime | None = json.get("timestamp", None)
        if not isinstance(timestamp, dt.datetime):
            raise ValueError("timestamp must be a datetime")
        screenshot: bytes | None = json.get("screenshot", None)
        space: ActionSpace | None = json.get("space", None)
        if not isinstance(space, dict):
            raise ValueError("space must be a dictionary")
        return Observation(
            url=url,
            title=title,
            timestamp=timestamp,
            screenshot=screenshot,
            _space=ActionSpace.from_json(space),
        )

    @staticmethod
    def from_snapshot(snapshot: BrowserSnapshot, space: ActionSpace | None = None, data: str = "") -> "Observation":
        return Observation(
            title=snapshot.title,
            url=snapshot.url,
            timestamp=snapshot.timestamp,
            screenshot=snapshot.screenshot,
            _space=space,
            data=data,
        )


# @dataclass
# class PreObservation(Observation):
#     _space: ActionSpace | None = None  # type: ignore

#     @property
#     @override
#     def space(self) -> ActionSpace:
#         raise ValueError("space is not available for pre-observations")
