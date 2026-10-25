"""Where each element sits on the page: the titles of the sections and items around it.

Two "Add to cart" buttons, one in the product's own panel and one under "Complete with" for an accessory,
have the same name. Their context tells them apart ("Complete with › SOLHETTA LED bulb"): in each enclosing
container, the heading before the element, and the name of a named container (a form, a group) around it.
`act()` shows it only for elements whose name is not unique on the page (see `notte_core.act.space`).
"""

from collections.abc import Callable

from notte_core.dom_tree import DomNode

# containers whose accessible name titles what they hold
_NAMED_CONTAINERS = frozenset(
    {
        "region",
        "navigation",
        "form",
        "search",
        "dialog",
        "alertdialog",
        "tabpanel",
        "article",
        "complementary",
        "group",
        "radiogroup",
        "table",
        "grid",
    }
)
# containers that start a context of their own: the titles around them say nothing about what they hold
_LANDMARKS = frozenset({"main", "banner", "contentinfo", "navigation", "complementary", "dialog", "alertdialog"})
# titles kept per element: the innermost ones
MAX_TITLES = 2
MAX_TITLE_LENGTH = 60
SEPARATOR = " › "


def _text(node: DomNode) -> str:
    return " ".join(" ".join(n.text for n in node.flatten() if n.get_role_str() == "text").split())


def _cut(text: str) -> str:
    return text if len(text) <= MAX_TITLE_LENGTH else text[:MAX_TITLE_LENGTH].rstrip() + "…"


def shorten(context: str, mask: Callable[[str], str]) -> str:
    """`context` as shown to a model: masked first (a title can echo a protected value, whose cut prefix no longer
    matches it), then each title cut to `MAX_TITLE_LENGTH`."""
    return SEPARATOR.join(_cut(title) for title in mask(context).split(SEPARATOR))


class _Headings:
    """Per node: the text of the last heading it holds, whether it holds an element outside its headings (then it
    is a section or an item of its own, and its headings title only what it holds), and how many elements it holds."""

    def __init__(self, root: DomNode) -> None:
        self.last: dict[int, str | None] = {}
        self.elements: dict[int, bool] = {}
        self.count: dict[int, int] = {}
        # each node's role, read once
        self.role: dict[int, str] = {}
        # breadth-first, without recursion (real pages nest deeper than recursion handles comfortably): read
        # backwards, every node comes after its children
        nodes = [root]
        for node in nodes:
            nodes.extend(node.children)
        for node in reversed(nodes):
            key = id(node)
            role = self.role[key] = node.get_role_str()
            count = int(node.id is not None)
            for child in node.children:
                count += self.count[id(child)]
            self.count[key] = count
            if role == "heading":
                # kept whole: titles are cut when shown, after masking (`shorten`)
                self.last[key] = _text(node) or None
                self.elements[key] = False
                continue
            last: str | None = None
            elements = node.id is not None
            for child in node.children:
                last = self.last[id(child)] or last
                elements = elements or self.elements[id(child)]
            self.last[key] = last
            self.elements[key] = elements

    def title(self, node: DomNode) -> str | None:
        """The title `node` gives to the siblings after it: a heading, or a block that holds a heading and no
        element (the header of a section, a card's title block)."""
        key = id(node)
        if self.role[key] == "heading" or not self.elements[key]:
            return self.last[key]
        return None


def element_contexts(root: DomNode) -> dict[str, str]:
    """The context of every element of the tree, by element id: its innermost `MAX_TITLES` titles, outermost
    first. Elements without any title are left out."""
    headings = _Headings(root)
    contexts: dict[str, str] = {}
    stack: list[tuple[DomNode, tuple[str, ...]]] = [(root, ())]
    while stack:
        node, around = stack.pop()
        if node.id is not None and around:
            contexts[node.id] = SEPARATOR.join(around[-MAX_TITLES:])
        role = headings.role[id(node)]
        if role in _LANDMARKS:
            around = ()
        if node.id is None and role in _NAMED_CONTAINERS:
            around = _append(around, " ".join(node.text.split()))
        current: str | None = None
        previous: DomNode | None = None
        children: list[tuple[DomNode, tuple[str, ...]]] = []
        for child in node.children:
            # a part of the page without elements has no context to give: only its title is read (below)
            if headings.count[id(child)] > 0:
                titles = _append(around, current)
                if previous is not None and headings.last[id(child)] is None and headings.count[id(child)] == 1:
                    # a lone element without a heading (a card's button) is titled by the block right before it that
                    # has one (the card's name, price and links), as both belong to the same item
                    titles = _append(titles, headings.last[id(previous)])
                # a heading titles the siblings after it, not itself
                children.append((child, titles))
            current = headings.title(child) or current
            previous = child
        stack.extend(reversed(children))
    return contexts


def _append(around: tuple[str, ...], title: str | None) -> tuple[str, ...]:
    if not title or (len(around) > 0 and around[-1] == title):
        return around
    return (*around, title)
