import datetime as dt
from dataclasses import dataclass, field

from notte.browser.node_type import A11yTree
from notte.pipe.preprocessing.a11y.traversal import set_of_interactive_nodes
from notte.utils.url import clean_url


@dataclass
class SnapshotMetadata:
    title: str
    url: str
    timestamp: dt.datetime = field(default_factory=dt.datetime.now)


@dataclass
class BrowserSnapshot:
    metadata: SnapshotMetadata
    html_content: str
    a11y_tree: A11yTree
    screenshot: bytes | None
    timestamp: dt.datetime = field(default_factory=dt.datetime.now)

    @property
    def clean_url(self) -> str:
        return clean_url(self.metadata.url)

    def compare_with(self, other: "BrowserSnapshot") -> bool:
        inodes = set_of_interactive_nodes(self.a11y_tree.simple)
        new_inodes = set_of_interactive_nodes(other.a11y_tree.simple)
        return inodes == new_inodes
