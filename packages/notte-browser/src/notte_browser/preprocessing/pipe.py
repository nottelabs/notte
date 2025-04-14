from enum import Enum
from typing import Self, final

from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.config import FrozenConfig

from notte_browser.preprocessing.a11y.pipe import (
    A11yPreprocessingConfig,
    A11yPreprocessingPipe,
)
from notte_browser.preprocessing.dom.pipe import DomPreprocessingPipe


class PreprocessingType(Enum):
    A11Y = "a11y"
    DOM = "dom"


class PreprocessingConfig(FrozenConfig):
    type: PreprocessingType = PreprocessingType.DOM
    a11y: A11yPreprocessingConfig = A11yPreprocessingConfig()

    def accessibility(self: Self) -> Self:
        return self._copy_and_validate(type=PreprocessingType.A11Y)

    def dom(self: Self) -> Self:
        return self._copy_and_validate(type=PreprocessingType.DOM)


@final
class ProcessedSnapshotPipe:
    @staticmethod
    def forward(snapshot: BrowserSnapshot, config: PreprocessingConfig) -> BrowserSnapshot:
        match config.type:
            case PreprocessingType.A11Y:
                return A11yPreprocessingPipe.forward(snapshot, config.a11y)
            case PreprocessingType.DOM:
                return DomPreprocessingPipe.forward(snapshot)
