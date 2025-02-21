from typing import Literal, final

from pydantic import BaseModel

from notte.browser.dom_tree import DomNode
from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
from notte.browser.snapshot import BrowserSnapshot
from notte.pipe.preprocessing.a11y.pruning import PruningConfig
from notte.pipe.preprocessing.a11y.tree import ProcessedA11yTree


class A11yPreprocessingConfig(BaseModel):
    tree_type: Literal["processed", "raw"] = "processed"
    pruning: PruningConfig = PruningConfig()


@final
class A11yPreprocessingPipe:

    @staticmethod
    def forward(
        snapshot: BrowserSnapshot,
        config: A11yPreprocessingConfig,
    ) -> ProcessedBrowserSnapshot:
        processed_tree = ProcessedA11yTree.from_a11y_tree(snapshot.a11y_tree, config.pruning)
        dom_node = DomNode.from_a11y_node(
            node=processed_tree.tree(type=config.tree_type),
            notte_selector=snapshot.metadata.url,
        )
        return ProcessedBrowserSnapshot(
            snapshot=snapshot,
            node=dom_node,
        )
