import datetime as dt
from dataclasses import dataclass, field

from notte.actions.space import ActionSpace
from notte.browser.node_type import clean_url
from notte.browser.snapshot import BrowserSnapshot

try:
    from PIL import Image
except ImportError:
    Image = None


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

    def display_screenshot(self) -> "Image.Image | None":
        from notte.utils.image import image_from_bytes

        if self.screenshot is None:
            return None
        return image_from_bytes(self.screenshot)

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
