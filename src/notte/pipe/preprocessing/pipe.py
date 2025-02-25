from enum import Enum
from typing import final

from pydantic import BaseModel

from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
from notte.browser.snapshot import BrowserSnapshot
from notte.pipe.preprocessing.a11y.pipe import (
    A11yPreprocessingConfig,
    A11yPreprocessingPipe,
)
from notte.pipe.preprocessing.dom.pipe import DomPreprocessingPipe


class PreprocessingType(Enum):
    A11Y = "a11y"
    DOM = "dom"


class PreprocessingConfig(BaseModel):
    type: PreprocessingType = PreprocessingType.DOM
    a11y: A11yPreprocessingConfig = A11yPreprocessingConfig()


@final
class ProcessedSnapshotPipe:
    @staticmethod
    def forward(snapshot: BrowserSnapshot, config: PreprocessingConfig) -> ProcessedBrowserSnapshot:
        match config.type:
            case PreprocessingType.A11Y:
                return A11yPreprocessingPipe.forward(snapshot, config.a11y)
            case PreprocessingType.DOM:
                return DomPreprocessingPipe.forward(snapshot)
