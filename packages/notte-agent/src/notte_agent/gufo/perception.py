from notte_core.space import ActionSpace
from typing_extensions import override

from notte_agent.falco.perception import FalcoPerception


class GufoPerception(FalcoPerception):
    @override
    def perceive_actions(self, space: ActionSpace) -> str:
        # same as falco, but use markdown description instead of html
        return space.markdown
