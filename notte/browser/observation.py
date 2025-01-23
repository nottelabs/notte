from dataclasses import dataclass

from notte.actions.space import ActionSpace
from notte.browser.snapshot import BrowserSnapshot, SnapshotMetadata
from notte.data.space import DataSpace
from notte.errors.processing import InvalidInternalCheckError
from notte.utils.url import clean_url

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore


@dataclass
class Observation:
    metadata: SnapshotMetadata
    screenshot: bytes | None = None
    _space: ActionSpace | None = None
    data: DataSpace | None = None

    @property
    def clean_url(self) -> str:
        return clean_url(self.metadata.url)

    @property
    def space(self) -> ActionSpace:
        if self._space is None:
            raise InvalidInternalCheckError(
                check="Space is not available for this observation",
                url=self.metadata.url,
                dev_advice=(
                    "observations with empty space should only be created by `env.goto`. "
                    "If you need a space for your observation, you should create it by calling `env.observe`."
                ),
            )
        return self._space

    @space.setter
    def space(self, space: ActionSpace) -> None:
        self._space = space

    def has_space(self) -> bool:
        return self._space is not None

    def has_data(self) -> bool:
        return self.data is not None

    def display_screenshot(self) -> "Image.Image | None":
        from notte.utils.image import image_from_bytes

        if self.screenshot is None:
            return None
        return image_from_bytes(self.screenshot)

    @staticmethod
    def from_snapshot(
        snapshot: BrowserSnapshot, space: ActionSpace | None = None, data: DataSpace | None = None
    ) -> "Observation":
        return Observation(
            metadata=snapshot.metadata,
            screenshot=snapshot.screenshot,
            _space=space,
            data=data,
        )
