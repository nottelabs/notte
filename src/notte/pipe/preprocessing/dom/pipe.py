from notte.browser.snapshot import BrowserSnapshot


class DomPreprocessingPipe:
    @staticmethod
    def forward(snapshot: BrowserSnapshot) -> BrowserSnapshot:
        return BrowserSnapshot(
            metadata=snapshot.metadata,
            html_content=snapshot.html_content,
            a11y_tree=snapshot.a11y_tree,
            dom_node=snapshot.dom_node,
            screenshot=snapshot.screenshot,
        )
