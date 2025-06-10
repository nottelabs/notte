from __future__ import annotations

from typing import ClassVar

from notte_core.browser.dom_tree import (
    ComputedDomAttributes,
    DomAttributes,
    DomNode,
    NodeSelectors,
)
from notte_core.browser.node_type import NodeRole, NodeType
from notte_core.browser.snapshot import (
    BrowserDialog,
    BrowserSnapshot,
    SnapshotMetadata,
    ViewportData,
)
from patchright.async_api import (
    Dialog,
)


class BrowserDialogHandler:
    DISMISS_ID: ClassVar[str] = "B400"
    ACCEPT_ID: ClassVar[str] = "B500"
    FILL_ID: ClassVar[str] = "I100"

    @staticmethod
    def dialog_snapshot(dialog: Dialog) -> BrowserSnapshot:
        # Returns dialog's type, can be one of `alert`, `beforeunload`, `confirm` or `prompt`.

        dialog_nodes: list[DomNode]
        match dialog.type:
            case "alert":
                dialog_nodes = BrowserDialogHandler.alert_nodes()
            case "confirm":
                dialog_nodes = BrowserDialogHandler.confirm_nodes()
            case "prompt":
                dialog_nodes = BrowserDialogHandler.prompt_nodes()
            case _:
                raise ValueError

        browser_dialog = BrowserDialog(type=dialog.type, message=dialog.message, nodes=dialog_nodes)
        return BrowserSnapshot(
            metadata=SnapshotMetadata(
                title="",
                url="",
                viewport=ViewportData(
                    scroll_x=0, scroll_y=0, viewport_width=0, viewport_height=0, total_width=0, total_height=0
                ),
                tabs=[],
            ),
            html_content="",
            a11y_tree=None,
            dom_node=DomNode(
                id=None,
                type=NodeType.OTHER,
                role="dialog",
                text="",
                children=[
                    DomNode(
                        id=None,
                        type=NodeType.TEXT,
                        role="text",
                        text=dialog.message,
                        children=[],
                        attributes=DomAttributes.safe_init(tag_name="p"),
                        computed_attributes=ComputedDomAttributes(
                            in_viewport=True,
                            is_interactive=False,
                            is_top_element=False,
                            is_editable=False,
                            shadow_root=False,
                            selectors=NodeSelectors(
                                css_selector="p",
                                xpath_selector="p",
                                notte_selector="",
                                playwright_selector="p",
                                iframe_parent_css_selectors=[],
                                in_iframe=False,
                                in_shadow_root=False,
                            ),
                        ),
                    ),
                    *dialog_nodes,
                ],
                attributes=DomAttributes.safe_init(tag_name="div"),
                computed_attributes=ComputedDomAttributes(
                    in_viewport=True,
                    is_interactive=False,
                    is_top_element=True,
                    is_editable=False,
                    shadow_root=False,
                    selectors=NodeSelectors(
                        css_selector="div",
                        xpath_selector="div",
                        notte_selector="",
                        playwright_selector="div",
                        iframe_parent_css_selectors=[],
                        in_iframe=False,
                        in_shadow_root=False,
                    ),
                ),
            ),
            screenshot=b"",
            browser_dialog=browser_dialog,
        )

    @staticmethod
    def prompt_nodes() -> list[DomNode]:
        return [
            DomNode(
                id=BrowserDialogHandler.FILL_ID,
                type=NodeType.INTERACTION,
                role=NodeRole.TEXTBOX,
                text="YOUR RESPONSE",
                children=[],
                attributes=DomAttributes.safe_init(tag_name="input", placeholder="input your response here"),
                computed_attributes=ComputedDomAttributes(
                    in_viewport=True,
                    is_interactive=True,
                    is_top_element=True,
                    is_editable=True,
                    shadow_root=False,
                    selectors=NodeSelectors(
                        css_selector="input",
                        xpath_selector="input",
                        notte_selector="",
                        playwright_selector="input",
                        iframe_parent_css_selectors=[],
                        in_iframe=False,
                        in_shadow_root=False,
                    ),
                ),
            ),
        ]

    @staticmethod
    def alert_nodes() -> list[DomNode]:
        return [
            DomNode(
                id=BrowserDialogHandler.DISMISS_ID,
                type=NodeType.INTERACTION,
                role="button",
                text="",
                children=[
                    DomNode(
                        id=None,
                        type=NodeType.TEXT,
                        role="text",
                        text="DISMISS",
                        children=[],
                        attributes=DomAttributes.safe_init(tag_name="p"),
                        computed_attributes=ComputedDomAttributes(
                            in_viewport=True,
                            is_interactive=False,
                            is_top_element=False,
                            is_editable=False,
                            shadow_root=False,
                            selectors=NodeSelectors(
                                css_selector="p",
                                xpath_selector="p",
                                notte_selector="",
                                playwright_selector="p",
                                iframe_parent_css_selectors=[],
                                in_iframe=False,
                                in_shadow_root=False,
                            ),
                        ),
                    ),
                ],
                attributes=DomAttributes.safe_init(tag_name="button"),
                computed_attributes=ComputedDomAttributes(
                    in_viewport=True,
                    is_interactive=True,
                    is_top_element=False,
                    is_editable=False,
                    shadow_root=False,
                    selectors=NodeSelectors(
                        css_selector="button",
                        xpath_selector="button",
                        notte_selector="",
                        playwright_selector="div",
                        iframe_parent_css_selectors=[],
                        in_iframe=False,
                        in_shadow_root=False,
                    ),
                ),
            ),
        ]

    @staticmethod
    def confirm_nodes() -> list[DomNode]:
        return [
            DomNode(
                id=BrowserDialogHandler.ACCEPT_ID,
                type=NodeType.INTERACTION,
                role="button",
                text="",
                children=[
                    DomNode(
                        id=None,
                        type=NodeType.TEXT,
                        role="text",
                        text="ACCEPT",
                        children=[],
                        attributes=DomAttributes.safe_init(tag_name="p"),
                        computed_attributes=ComputedDomAttributes(
                            in_viewport=True,
                            is_interactive=False,
                            is_top_element=False,
                            is_editable=False,
                            shadow_root=False,
                            selectors=NodeSelectors(
                                css_selector="p",
                                xpath_selector="p",
                                notte_selector="",
                                playwright_selector="p",
                                iframe_parent_css_selectors=[],
                                in_iframe=False,
                                in_shadow_root=False,
                            ),
                        ),
                    ),
                ],
                attributes=DomAttributes.safe_init(tag_name="button"),
                computed_attributes=ComputedDomAttributes(
                    in_viewport=True,
                    is_interactive=True,
                    is_top_element=False,
                    is_editable=False,
                    shadow_root=False,
                    selectors=NodeSelectors(
                        css_selector="button",
                        xpath_selector="button",
                        notte_selector="",
                        playwright_selector="button",
                        iframe_parent_css_selectors=[],
                        in_iframe=False,
                        in_shadow_root=False,
                    ),
                ),
            ),
            DomNode(
                id=BrowserDialogHandler.DISMISS_ID,
                type=NodeType.INTERACTION,
                role="button",
                text="",
                children=[
                    DomNode(
                        id=None,
                        type=NodeType.TEXT,
                        role="text",
                        text="DISMISS",
                        children=[],
                        attributes=DomAttributes.safe_init(tag_name="p"),
                        computed_attributes=ComputedDomAttributes(
                            in_viewport=True,
                            is_interactive=False,
                            is_top_element=False,
                            is_editable=False,
                            shadow_root=False,
                            selectors=NodeSelectors(
                                css_selector="p",
                                xpath_selector="p",
                                notte_selector="",
                                playwright_selector="p",
                                iframe_parent_css_selectors=[],
                                in_iframe=False,
                                in_shadow_root=False,
                            ),
                        ),
                    ),
                ],
                attributes=DomAttributes.safe_init(tag_name="button"),
                computed_attributes=ComputedDomAttributes(
                    in_viewport=True,
                    is_interactive=True,
                    is_top_element=False,
                    is_editable=False,
                    shadow_root=False,
                    selectors=NodeSelectors(
                        css_selector="button",
                        xpath_selector="button",
                        notte_selector="",
                        playwright_selector="div",
                        iframe_parent_css_selectors=[],
                        in_iframe=False,
                        in_shadow_root=False,
                    ),
                ),
            ),
        ]
