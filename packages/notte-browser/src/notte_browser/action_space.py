from notte_core.actions import ActionParameter, ClickAction, FillAction, InteractionAction, SelectDropdownOptionAction
from notte_core.config import config
from notte_core.dom_tree import DomNode
from notte_core.errors import InvalidInternalCheckError
from notte_core.logging import logger
from notte_core.node_type import NodeRole, NodeType
from notte_core.space import ActionSpace


def build_action_space(dom_node: DomNode) -> ActionSpace:
    """List the interaction actions available on a page from its DOM, without any LLM call.

    The description renders the page's interactive elements (attributes cut to 60 characters, and
    only the open dialogs when the page has some), and every interaction node becomes one action.
    Disabled controls are rendered without an id (`_[:]<button disabled>Send</button>`) and offer no action, as
    are the links, buttons, fields and options above or below the viewport, with fewer attributes
    (`_[:]<a>About</a>`).
    """
    description = render_interactions(
        dom_node,
        max_len_per_attribute=60,
        verbose=config.verbose,
    )
    return ActionSpace(
        description=description,
        interaction_actions=[_interaction_action(node) for node in dom_node.interaction_nodes()],
    )


def _interaction_action(node: DomNode) -> InteractionAction:
    assert node.id is not None, "Interaction nodes must have an id"
    if node.computed_attributes.selectors is None:
        raise InvalidInternalCheckError(
            check="Node should have an xpath selector",
            url=node.get_url(),
            dev_advice="This should never happen.",
        )
    label = node.inner_text()
    if node.id.startswith("I"):
        param = ActionParameter(name="value", type="string")
        if node.get_role_str() == "combobox" and not node.computed_attributes.is_editable:
            action = SelectDropdownOptionAction(
                id=node.id,
                value="<sample_value>",
                text_label=label,
                press_enter=False,
            )
        else:
            # Historically fill labels were read from a childless copy: only inputs retained a label.
            action = FillAction(
                id=node.id,
                value="<sample_value>",
                text_label=label if node.attributes is not None and node.attributes.tag_name.lower() == "input" else "",
                press_enter=False,
            )
    elif node.id.startswith("O"):
        param = None
        action = SelectDropdownOptionAction(id=node.id, value=node.id, text_label=label)
    else:
        param = None
        action = ClickAction(id=node.id, text_label=label)
    action.selector = node.computed_attributes.selectors
    action.accessible_name = node.accessible_name
    action.description = render_node(node, include_children=False)
    action.category = "Interaction action"
    action.param = param
    return action


INCLUDE_ATTRIBUTES: frozenset[str] = frozenset(
    [
        "title",
        "type",
        "name",
        "role",
        "tabindex",
        "aria_label",
        "placeholder",
        "value",
        "alt",
        "src",
        "href",
        "aria_expanded",
    ]
)

# an element above or below the viewport is rendered with what says what it is (its tag and `role`, an input's
# `type`, and its text, or its name when it has no text), not where it goes: a long page has hundreds of them
# (`href` and `title` would double the description of a Wikipedia article), and they offer no action until
# scrolled to
OFFSCREEN_NAME_ATTRIBUTES: frozenset[str] = frozenset(["aria_label", "title", "alt", "placeholder", "value"])


def render_node(
    node: DomNode,
    max_len_per_attribute: int | None = None,
    *,
    include_children: bool = True,
) -> str:
    if node.id is None and not node.disabled and not node.offscreen:
        raise InvalidInternalCheckError(
            check="Node should have an id, or be disabled or off-screen",
            url=node.get_url(),
            dev_advice="This should never happen.",
        )
    attrs = node.attributes
    if attrs is None:
        raise ValueError(f"Attributes are None for node: {node}")
    if include_children:
        children_str = "\n".join(children_texts(node)).strip()
    else:
        # Action descriptions used childless copies with text=inner_text(), without attribute truncation.
        children_str = node.inner_text().strip() if node.get_role_str() == "text" else ""
    include_attributes = INCLUDE_ATTRIBUTES
    if node.offscreen:
        include_attributes = frozenset(["role", "type"] if attrs.tag_name.lower() == "input" else ["role"])
        if len(children_str) == 0:
            include_attributes = include_attributes | OFFSCREEN_NAME_ATTRIBUTES
            if not _named_by_attributes(node):
                # only images or icons inside: their name (`<a><img alt="Home"></a>` is rendered `<a>Home</a>`)
                children_str = (node.accessible_name or "").strip()
    attrs_str = ""
    attrs_relevant = attrs.relevant_attrs(
        include_attributes=include_attributes,
        max_len_per_attribute=max_len_per_attribute,
    )
    if len(attrs_relevant) > 0:
        attrs_str = " " + " ".join([f'{key}="{value}"' for key, value in attrs_relevant.items()])
    if node.disabled:
        attrs_str += " disabled"
    return f"<{attrs.tag_name}{attrs_str}>{children_str}</{attrs.tag_name}>"


def format_node(
    node: DomNode,
    node_texts: list[str],
    max_len_per_attribute: int | None,
    is_parent_interaction: bool = False,
) -> list[str]:
    if node.type.value == NodeType.TEXT.value:
        if len(node.children) > 0:
            raise InvalidInternalCheckError(
                check="Text node should not have children",
                url=node.get_url(),
                dev_advice="This should never happen.",
            )
        # Add text only if it doesn't have a highlighted parent
        if not is_parent_interaction and len(node.text.strip()) > 0:
            node_texts.append(f"_[:]{node.text.strip()}")
    else:
        # Add element with highlight_index
        if node.id is not None:
            is_parent_interaction = True
            html_description = render_node(node, max_len_per_attribute)
            node_texts.append(f"{node.id}[:]{html_description}")
        elif node.disabled or (node.offscreen and not _unnamed_offscreen(node)):
            # described (with its text) like an interactive element, but without an id to act on
            is_parent_interaction = True
            node_texts.append(f"_[:]{render_node(node, max_len_per_attribute)}")

        # Process children regardless
        for child in node.children:
            _ = format_node(
                node=child,
                node_texts=node_texts,
                max_len_per_attribute=max_len_per_attribute,
                is_parent_interaction=is_parent_interaction,
            )
    return node_texts


def _named_by_attributes(node: DomNode) -> bool:
    """It has a non-empty name attribute (`title=""` names nothing)."""
    if node.attributes is None:
        return False
    return any(str(value).strip() for value in node.attributes.relevant_attrs(OFFSCREEN_NAME_ATTRIBUTES).values())


def _unnamed_offscreen(node: DomNode) -> bool:
    """An off-screen link, button or option without text or name (a heading anchor, an unlabelled icon
    button): its rendering would not say what it is. Off-screen fields, checkboxes and radios are described
    even without a name, as in view: their label is the text next to them."""
    if node.attributes is not None and node.attributes.tag_name.lower() in ("input", "select", "textarea"):
        return False
    if isinstance(node.role, NodeRole) and node.role.short_id() == "I":
        return False
    named = _named_by_attributes(node) or len((node.accessible_name or "").strip()) > 0
    return not named and len(children_texts(node)) == 0


def children_texts(root_node: DomNode) -> list[str]:
    texts: list[str] = []

    def collect_text(node: DomNode) -> None:
        # Skip this branch if we hit a highlighted, disabled or off-screen element (except for the current node)
        if (node.id is not None or node.disabled or node.offscreen) and node is not root_node:
            return

        if node.get_role_str() == "text" and len(node.text.strip()) > 0:
            texts.append(node.text.strip())
        else:
            for child in node.children:
                collect_text(child)

    collect_text(root_node)
    return texts


def render_interactions(
    node: DomNode,
    max_len_per_attribute: int | None = None,
    verbose: bool = False,
) -> str:
    """Convert the processed DOM content to HTML."""
    component_node_strs: list[str] = []
    components = node.prune_non_dialogs_if_present()
    for component_node in components:
        formatted_text: list[str] = format_node(
            node=component_node,
            node_texts=[],
            max_len_per_attribute=max_len_per_attribute,
        )

        rendered_component = "\n".join(formatted_text).strip()
        if len(components) > 0:
            # more than 1 component => modals here add some special text to separate them
            rendered_component = f"""
### Content of '{component_node.get_role_str()}' component with text '{component_node.text}'
{rendered_component}
"""
        component_node_strs.append(rendered_component)

    rendered_node = "\n".join(component_node_strs).strip()
    if verbose:
        logger.trace(f"📄 Rendered node: \n{rendered_node}")
    return rendered_node
