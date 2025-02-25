from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
from notte.browser.snapshot import BrowserSnapshot


class DomPreprocessingPipe:
    @staticmethod
    def forward(snapshot: BrowserSnapshot) -> ProcessedBrowserSnapshot:
        return ProcessedBrowserSnapshot(
            snapshot=snapshot,
            node=snapshot.dom_node,
        )
