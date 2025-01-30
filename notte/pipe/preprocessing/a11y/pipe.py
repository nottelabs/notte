from typing import final

from notte.browser.dom_tree import DomNode
from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
from notte.browser.snapshot import BrowserSnapshot
from notte.pipe.preprocessing.a11y.tree import ProcessedA11yTree


@final
class A11yPreprocessingPipe:

    @staticmethod
    def forward(
        snapshot: BrowserSnapshot,
        tree_type: str = "processed",
    ) -> ProcessedBrowserSnapshot:
        processed_tree = ProcessedA11yTree.from_a11y_tree(snapshot.a11y_tree)
        dom_node = DomNode.from_a11y_node(
            node=processed_tree.tree(type=tree_type),
            notte_selector=snapshot.metadata.url,
        )
        return ProcessedBrowserSnapshot(
            snapshot=snapshot,
            node=dom_node,
        )
