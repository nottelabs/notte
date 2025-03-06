from typing import Literal, final

from notte.browser.dom_tree import DomNode
from notte.browser.snapshot import BrowserSnapshot
from notte.common.config import FrozenConfig
from notte.errors.base import AccessibilityTreeMissingError
from notte.pipe.preprocessing.a11y.pruning import PruningConfig
from notte.pipe.preprocessing.a11y.tree import ProcessedA11yTree


class A11yPreprocessingConfig(FrozenConfig):
    tree_type: Literal["processed", "raw"] = "processed"
    pruning: PruningConfig = PruningConfig()


@final
class A11yPreprocessingPipe:
    @staticmethod
    def forward(
        snapshot: BrowserSnapshot,
        config: A11yPreprocessingConfig,
    ) -> BrowserSnapshot:
        if snapshot.a11y_tree is None:
            raise AccessibilityTreeMissingError()

        processed_tree = ProcessedA11yTree.from_a11y_tree(snapshot.a11y_tree, config.pruning)
        dom_node = DomNode.from_a11y_node(
            node=processed_tree.tree(type=config.tree_type),
            notte_selector=snapshot.metadata.url,
        )
        return snapshot.with_dom_node(dom_node)
