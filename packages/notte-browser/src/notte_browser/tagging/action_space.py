from notte_core.actions import ActionParameter, InteractionAction
from notte_core.browser.dom_tree import DomNode, InteractionDomNode
from notte_core.common.config import config
from notte_core.errors.processing import InvalidInternalCheckError
from notte_core.space import ActionSpace

from notte_browser.rendering.interaction_only import InteractionOnlyDomNodeRenderingPipe
from notte_browser.tagging.type import PossibleAction


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


def _interaction_action(node: InteractionDomNode) -> InteractionAction:
    if node.computed_attributes.selectors is None:
        raise InvalidInternalCheckError(
            check="Node should have an xpath selector",
            url=node.get_url(),
            dev_advice="This should never happen.",
        )
    # rendered again rather than reused from the description: here attributes are not cut, and a
    # node outside the open dialogs is not in the description at all
    action = PossibleAction(
        id=node.id,
        category="Interaction action",
        description=InteractionOnlyDomNodeRenderingPipe.render_node(node),
        param=ActionParameter(name="value", type="string") if node.id.startswith("I") else None,
    )
    return action.to_interaction(node)
