import operator
from functools import reduce
from typing import Annotated, Any

from notte_core.common.notifier import BaseNotifier
from pydantic import Field, create_model

from notte_integrations.notifiers.discord import DiscordNotifier
from notte_integrations.notifiers.mail import EmailNotifier
from notte_integrations.notifiers.slack import SlackNotifier

NOTIFIERS = [SlackNotifier, DiscordNotifier, EmailNotifier]


def notifier_from_dump(dump: dict[Any, Any]) -> "BaseNotifier":
    # load all integration classes
    import notte_integrations.notifiers as _  # noqa: F401

    NotifierUnion = Annotated[reduce(operator.or_, BaseNotifier.REGISTRY.values()), Field(discriminator="type")]  # noqa: F821
    NotifierHolder = create_model("NotifierHolder", notifier=NotifierUnion)

    return NotifierHolder.model_validate(dict(notifier=dump)).notifier  # pyright: ignore [reportAttributeAccessIssue, reportUnknownVariableType, reportUnknownMemberType]
