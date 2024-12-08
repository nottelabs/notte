from dataclasses import dataclass

from notte.browser.node_type import A11yTree


@dataclass
class BrowserSnapshot:
    url: str
    html_content: str
    a11y_tree: A11yTree
    screenshot: bytes | None

    @property
    def clean_url(self) -> str:
        # remove anything after ? i.. ?tfs=CBwQARooEgoyMDI0LTEyLTAzagwIAh
        return self.url.split("?")[0]
