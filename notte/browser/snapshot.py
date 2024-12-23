import datetime as dt
from dataclasses import dataclass, field

from notte.browser.node_type import A11yTree, clean_url


@dataclass
class BrowserSnapshot:
    title: str
    url: str
    html_content: str
    a11y_tree: A11yTree
    screenshot: bytes | None
    timestamp: dt.datetime = field(default_factory=dt.datetime.now)

    @property
    def clean_url(self) -> str:
        return clean_url(self.url)
