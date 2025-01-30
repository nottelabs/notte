from enum import Enum
from typing import final

from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
from notte.browser.snapshot import BrowserSnapshot
from notte.pipe.preprocessing.a11y.pipe import A11yPreprocessingPipe
from notte.pipe.preprocessing.dom.pipe import DomPreprocessingPipe


class PreprocessingType(Enum):
    A11Y = "a11y"
    DOM = "dom"


@final
class ProcessedSnapshotPipe:

    @staticmethod
    def forward(snapshot: BrowserSnapshot, type: PreprocessingType) -> ProcessedBrowserSnapshot:
        match type:
            case PreprocessingType.A11Y:
                return A11yPreprocessingPipe.forward(snapshot)
            case PreprocessingType.DOM:
                return DomPreprocessingPipe.forward(snapshot)
