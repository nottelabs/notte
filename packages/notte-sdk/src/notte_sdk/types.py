"""Public SDK types: generated resources and shared core page-operation domain types.

Resource names migrate individually. Actions, observations, execution results and scrape
results retain their core identity for local/cloud interoperability.
"""

from notte_core.types import *  # noqa: F403  # pyright: ignore[reportWildcardImportFromLibrary]

from notte_sdk._compat.profiles import ProfileListRequest as ProfileListRequest
from notte_sdk._compat.profiles import ProfileResponse as ProfileResponse
from notte_sdk._generated.models import ProfileCreateRequest as ProfileCreateRequest
from notte_sdk._generated.typing import ProfileCreateRequestDict as ProfileCreateRequestDict
from notte_sdk._generated.typing import ProfileListRequestDict as ProfileListRequestDict
