from notte_core.common.config import PerceptionType
from notte_core.space import ActionSpace
from typing_extensions import override

from notte_agent.falco.perception import FalcoPerception


class GufoPerception(FalcoPerception):
    @property
    @override
    def perception_type(self) -> PerceptionType:
        return PerceptionType.DEEP

    @override
    def perceive_actions(self, space: ActionSpace) -> str:
        # same as falco, but use markdown description instead of html
        return space.markdown
