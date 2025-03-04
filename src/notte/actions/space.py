from collections.abc import Sequence
from typing import Protocol, Self, final

from loguru import logger
from pydantic import BaseModel, Field
from typing_extensions import override

from notte.actions.base import Action, BrowserAction, PossibleAction
from notte.controller.actions import AllActionRole, AllActionStatus
from notte.controller.space import BaseActionSpace
from notte.errors.actions import InvalidActionError
from notte.errors.processing import InvalidInternalCheckError


class SentenceTransformerProtocol(Protocol):
    def encode(self, query: str | list[str], convert_to_numpy: bool = True) -> "npt.NDArray[np.float32]": ...


# Move numpy imports inside try block
try:
    import numpy as np
    import numpy.typing as npt
    from sentence_transformers import SentenceTransformer  # type: ignore[import]

    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False  # type: ignore


def check_embedding_imports():
    if not EMBEDDING_AVAILABLE:
        raise ImportError(
            (
                "The 'numpy' and `sentence-transformers` packages are required for embeddings."
                " Install them with 'uv sync --extra embeddings'"
            )
        )


class PossibleActionSpace(BaseModel):
    description: str
    actions: Sequence[PossibleAction]


class ActionSpace(BaseActionSpace):
    raw_actions: Sequence[Action] = Field(description="List of available actions in the current state", exclude=True)
    _embeddings: "npt.NDArray[np.float32] | None" = None

    def __post_init__(self) -> None:
        # filter out special actions
        nb_original_actions = len(self.raw_actions)
        self.raw_actions = [action for action in self.raw_actions if not BrowserAction.is_special(action.id)]
        if len(self.raw_actions) != nb_original_actions:
            logger.warning(
                (
                    "Special actions are not allowed in the action space. "
                    f"Removed {nb_original_actions - len(self.raw_actions)} actions."
                )
            )

        for action in self.raw_actions:
            # check 1: check action id is valid
            if action.role == "other":
                raise InvalidActionError(
                    action.id,
                    f"actions listed in action space should have a valid role (L, B, I), got '{action.id[0]}' .",
                )
            # check 2: actions should have description
            if len(action.description) == 0:
                raise InvalidActionError(action.id, "actions listed in action space should have a description.")

    @override
    def actions(
        self,
        status: AllActionStatus = "valid",
        role: AllActionRole = "all",
        include_browser: bool = False,
    ) -> Sequence[Action]:
        match (status, role):
            case ("all", "all"):
                actions = list(self.raw_actions)
            case ("all", _):
                actions = [action for action in self.raw_actions if action.role == role]
            case (_, "all"):
                actions = [action for action in self.raw_actions if action.status == status]
            case (_, _):
                actions = [action for action in self.raw_actions if action.status == status and action.role == role]

        if include_browser:
            return actions + BrowserAction.list()
        return actions

    @override
    def browser_actions(self) -> Sequence[BrowserAction]:
        return BrowserAction.list()

    def search(self, query: str, threshold: float = 0.60, max_results: int = 1) -> Sequence[Action]:
        check_embedding_imports()

        if self._embeddings is None:
            self._embeddings = ActionEmbedding().embed_actions(self.actions("valid"))

        # Perform similarity search
        action_embs = self._embeddings

        # Get query embedding
        query_embedding = ActionEmbedding().embed_query(query)

        # Calculate cosine similarities
        similarities: "npt.NDArray[np.float32]" = np.dot(action_embs, query_embedding) / (  # type: ignore[reportPossiblyUnboundVariable]
            np.linalg.norm(action_embs, axis=1) * np.linalg.norm(query_embedding)  # type: ignore[reportPossiblyUnboundVariable]
        )

        # Get indices of actions above threshold, sorted by similarity
        valid_indices = np.where(similarities >= threshold)[0]  # type: ignore
        sorted_indices = valid_indices[np.argsort(-similarities[valid_indices])]  # type: ignore

        # Return up to max_results actions
        result_indices = sorted_indices[:max_results]
        actions = [a for a in self.actions("valid") if a.status == "valid"]
        most_relevant_actions: list[Action] = [actions[i] for i in result_indices]
        return most_relevant_actions

    @override
    def markdown(self, status: AllActionStatus = "valid", include_browser: bool = True) -> str:
        # Get actions with requested status
        actions_to_format = self.actions(status, include_browser=include_browser)

        # Group actions by category
        grouped_actions: dict[str, list[Action]] = {}
        for action in actions_to_format:
            if len(action.category) == 0:
                # should not happen
                raise InvalidInternalCheckError(
                    check=f"action {action} has no category.",
                    url="unknown url",
                    dev_advice=(
                        "This should technically never happen due to post init checks in `notte.actions.space.py`."
                    ),
                )
            if action.category not in grouped_actions:
                grouped_actions[action.category] = []
            grouped_actions[action.category].append(action)

        # Build markdown output
        output: list[str] = []
        for category, actions in grouped_actions.items():
            if len(output) == 0:
                # no \n at the beginning
                output.append(f"# {category}")
            else:
                output.append(f"\n# {category}")
            # Sort actions by ID lexicographically
            sorted_actions = sorted(actions, key=lambda x: x.id)
            for action in sorted_actions:
                line = f"* {action.id}: {action.description}"
                if len(action.params) > 0:
                    line += f" ({action.params})"
                output.append(line)
        return "\n".join(output)


@final
class ActionEmbedding:
    _instance: Self | None = None
    _model: SentenceTransformerProtocol | None = None

    def __new__(cls) -> Self:
        check_embedding_imports()
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._model = SentenceTransformer("all-MiniLM-L6-v2")  # type: ignore[import]
        return cls._instance

    def embed_actions(self, actions: Sequence[Action]) -> "npt.NDArray[np.float32]":
        check_embedding_imports()
        descriptions = [action.embedding_description() for action in actions]
        if self._model is None:
            # should not happen
            raise InvalidInternalCheckError(
                check="embedding model not initialized",
                url="unknown url",
                dev_advice="This should technically never happen since `ActionEmbedding` is a singleton.",
            )
        return self._model.encode(descriptions, convert_to_numpy=True)

    def embed_query(self, query: str) -> "npt.NDArray[np.float32]":
        check_embedding_imports()
        if self._model is None:
            # should not happen
            raise InvalidInternalCheckError(
                check="embedding model not initialized",
                url="unknown url",
                dev_advice="This should technically never happen since `ActionEmbedding` is a singleton.",
            )
        return self._model.encode(query, convert_to_numpy=True)
