import nest_asyncio  # pyright: ignore[reportMissingTypeStubs]
import notte_core

notte_core.set_error_mode("developer")

_ = nest_asyncio.apply()  # pyright: ignore[reportUnknownMemberType]
