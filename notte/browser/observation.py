from dataclasses import dataclass
from typing import Any

from PIL import Image
from typing_extensions import override

from notte.actions.space import ActionSpace
from notte.utils import image


@dataclass
class Observation:
    _url: str
    _space: ActionSpace
    _screenshot: bytes | None = None

    @property
    def url(self) -> str:
        return self._url

    @property
    def clean_url(self) -> str:
        # remove anything after ? i.. ?tfs=CBwQARooEgoyMDI0LTEyLTAzagwIAh
        return self.url.split("?")[0]

    @property
    def space(self) -> ActionSpace:
        return self._space

    @property
    def screenshot(self) -> bytes | None:
        return self._screenshot

    def display_screenshot(self) -> Image.Image | None:
        if self.screenshot is None:
            return None
        return image.image_from_bytes(self.screenshot)

    @staticmethod
    def from_json(json: dict[str, Any]) -> "Observation":
        url: str | None = json.get("url", None)
        if not isinstance(url, str):
            raise ValueError("url must be a string")
        screenshot: bytes | None = json.get("screenshot", None)
        space: ActionSpace | None = json.get("space", None)
        if not isinstance(space, dict):
            raise ValueError("space must be a dictionary")
        return Observation(
            _url=url,
            _screenshot=screenshot,
            _space=ActionSpace.from_json(space),
        )


@dataclass
class PreObservation(Observation):
    _space: ActionSpace | None = None  # type: ignore

    @override
    @property
    def space(self) -> ActionSpace:
        raise ValueError("space is not available for pre-observations")
