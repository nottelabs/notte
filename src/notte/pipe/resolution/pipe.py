from loguru import logger
from typing_extensions import final

from notte.actions.base import ExecutableAction
from notte.browser.snapshot import BrowserSnapshot
from notte.browser.window import BrowserWindow
from notte.controller.actions import BaseAction, BrowserAction, InteractionAction
from notte.controller.proxy import NotteActionProxy
from notte.pipe.preprocessing.pipe import PreprocessingType
from notte.pipe.resolution.complex_resolution import ComplexActionNodeResolutionPipe
from notte.pipe.resolution.simple_resolution import SimpleActionResolutionPipe


@final
class NodeResolutionPipe:
    def __init__(self, window: BrowserWindow, type: PreprocessingType, verbose: bool = False) -> None:
        self.complex = ComplexActionNodeResolutionPipe(window=window)
        self.simple = SimpleActionResolutionPipe()
        self.type = type
        self.verbose = verbose

    async def forward(
        self,
        action: BaseAction,
        snapshot: BrowserSnapshot | None,
    ) -> InteractionAction | BrowserAction:
        match self.type:
            case PreprocessingType.A11Y:
                if not isinstance(action, ExecutableAction):
                    raise ValueError(
                        (
                            f"Action {action.id} is not an executable action. Cannot resolve it using A11y preprocessing"
                            " pipe."
                        )
                    )
                exec_action = await self.complex.forward(action, snapshot=snapshot)
                return NotteActionProxy.forward(exec_action)
            case PreprocessingType.DOM:
                if isinstance(action, ExecutableAction):
                    if action.node is None and snapshot is not None:
                        action.node = snapshot.dom_node.find(action.id)
                    action = NotteActionProxy.forward(action)
                    if self.verbose:
                        logger.info(f"Resolving to action {action.dump_str()}")

                return SimpleActionResolutionPipe.forward(action, snapshot=snapshot, verbose=self.verbose)  # type: ignore
