from notte_core.actions import (
    CaptchaSolveAction as CaptchaSolve,
)
from notte_core.actions import (
    CheckAction as Check,
)
from notte_core.actions import (
    ClickAction as Click,
)
from notte_core.actions import (
    CloseTabAction as CloseTab,
)
from notte_core.actions import (
    CompletionAction as Completion,
)
from notte_core.actions import (
    DownloadFileAction as DownloadFile,
)
from notte_core.actions import (
    EmailReadAction as EmailRead,
)
from notte_core.actions import (
    FallbackFillAction as FallbackFill,
)
from notte_core.actions import (
    FillAction as Fill,
)
from notte_core.actions import (
    FormFillAction as FormFill,
)
from notte_core.actions import (
    GoBackAction as GoBack,
)
from notte_core.actions import (
    GoForwardAction as GoForward,
)
from notte_core.actions import (
    GotoAction as Goto,
)
from notte_core.actions import (
    GotoNewTabAction as GotoNewTab,
)
from notte_core.actions import (
    HelpAction as Help,
)
from notte_core.actions import (
    InteractionActionUnion as InteractionActionUnion,
)
from notte_core.actions import (
    MultiFactorFillAction as MultiFactorFill,
)
from notte_core.actions import (
    PressKeyAction as PressKey,
)
from notte_core.actions import (
    ReloadAction as Reload,
)
from notte_core.actions import (
    ScrapeAction as Scrape,
)
from notte_core.actions import (
    ScrollDownAction as ScrollDown,
)
from notte_core.actions import (
    ScrollUpAction as ScrollUp,
)
from notte_core.actions import (
    SelectDropdownOptionAction as SelectDropdownOption,
)
from notte_core.actions import (
    SmsReadAction as SmsRead,
)
from notte_core.actions import (
    SwitchTabAction as SwitchTab,
)
from notte_core.actions import (
    UploadFileAction as UploadFile,
)
from notte_core.actions import (
    WaitAction as Wait,
)

# Define __all__ with only the renamed action classes and other important items
__all__ = [
    # Renamed action classes (without 'Action' suffix)
    "FormFill",
    "Goto",
    "GotoNewTab",
    "CloseTab",
    "SwitchTab",
    "GoBack",
    "GoForward",
    "Reload",
    "Wait",
    "PressKey",
    "ScrollUp",
    "ScrollDown",
    "CaptchaSolve",
    "Help",
    "Completion",
    "Scrape",
    "EmailRead",
    "SmsRead",
    "Click",
    "Fill",
    "MultiFactorFill",
    "FallbackFill",
    "Check",
    "SelectDropdownOption",
    "UploadFile",
    "DownloadFile",
]
