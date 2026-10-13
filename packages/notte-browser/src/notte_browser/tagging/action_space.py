from notte_core.actions import ActionParameter, ClickAction, FillAction, InteractionAction, SelectDropdownOptionAction
from notte_core.browser.dom_tree import DomNode
from notte_core.common.config import config
from notte_core.errors.processing import InvalidInternalCheckError
from notte_core.space import ActionSpace

from notte_browser.rendering.interaction_only import InteractionOnlyDomNodeRenderingPipe


def build_action_space(dom_node: DomNode) -> ActionSpace:
    """List the interaction actions available on a page from its DOM, without any LLM call.

    The description renders the page's interactive elements (attributes cut to 60 characters, and
    only the open dialogs when the page has some), and every interaction node becomes one action.
    """
    description = InteractionOnlyDomNodeRenderingPipe.forward(
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
    action.description = InteractionOnlyDomNodeRenderingPipe.render_node(node, include_children=False)
    action.category = "Interaction action"
    action.param = param
    return action
