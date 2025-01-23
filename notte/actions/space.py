import random
from dataclasses import dataclass
from enum import Enum
from typing import Literal, Self, final

from loguru import logger

from notte.actions.base import (
    Action,
    ActionRole,
    ActionStatus,
    PossibleAction,
    SpecialAction,
)
from notte.errors.actions import InvalidActionError
from notte.errors.processing import InvalidInternalCheckError

# Move numpy imports inside try block
try:
    import numpy as np
    import numpy.typing as npt
    from sentence_transformers import SentenceTransformer

    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False


def check_embedding_imports():
    if not EMBEDDING_AVAILABLE:
        raise ImportError(
            (
                "The 'numpy' and `sentence-transformers` packages are required for embeddings."
                " Install them with 'poetry install --with embeddings'"
            )
        )


class SpaceCategory(Enum):
    HOMEPAGE = "homepage"
    SEARCH_RESULTS = "search-results"
    DATA_FEED = "data-feed"
    ITEM = "item"
    AUTH = "auth"
    FORM = "form"
    MANAGE_COOKIES = "manage-cookies"
    OVERLAY = "overlay"
    PAYMENT = "payment"
    CAPTCHA = "captcha"
    OTHER = "other"

    def is_data(self) -> bool:
        return self.value in [
            SpaceCategory.DATA_FEED.value,
            SpaceCategory.SEARCH_RESULTS.value,
            SpaceCategory.ITEM.value,
        ]


@dataclass
class PossibleActionSpace:
    description: str
    actions: list[PossibleAction]


@dataclass
class ActionSpace:
    description: str
    _actions: list[Action]
    category: SpaceCategory | None = None
    _embeddings: "npt.NDArray[np.float32] | None" = None

    def __post_init__(self) -> None:
        # filter out special actions
        nb_original_actions = len(self._actions)
        self._actions = [action for action in self._actions if not SpecialAction.is_special(action.id)]
        if len(self._actions) != nb_original_actions:
            logger.warning(
                (
                    "Special actions are not allowed in the action space. "
                    f"Removed {nb_original_actions - len(self._actions)} actions."
                )
            )

        for action in self._actions:
            # check 1: check action id is valid
            if action.role == "other":
                raise InvalidActionError(
                    action.id,
                    f"actions listed in action space should have a valid role (L, B, I), got '{action.id[0]}' .",
                )
            # check 2: actions should have description
            if len(action.description) == 0:
                raise InvalidActionError(action.id, "actions listed in action space should have a description.")

    def with_actions(self, actions: list[Action]) -> "ActionSpace":
        return ActionSpace(
            description=self.description,
            _actions=actions,
            category=self.category,
        )

    def actions(
        self,
        status: Literal[ActionStatus, "all"] = "valid",
        role: Literal[ActionRole, "all"] = "all",
        include_special: bool = False,
    ) -> list[Action]:
        match (status, role):
            case ("all", "all"):
                actions = self._actions
            case ("all", _):
                actions = [action for action in self._actions if action.role == role]
            case (_, "all"):
                actions = [action for action in self._actions if action.status == status]
            case (_, _):
                actions = [action for action in self._actions if action.status == status and action.role == role]

        if include_special:
            actions += SpecialAction.list()  # type: ignore
        return actions

    def special_actions(self) -> list[SpecialAction]:
        return SpecialAction.list()  # type: ignore

    def sample(
        self,
        status: Literal[ActionStatus, "all"] = "valid",
        role: Literal[ActionRole, "all"] = "all",
    ) -> Action:
        action: Action = random.choice(self.actions(status, role))
        return Action(
            id=action.id,
            description=action.description,
            category=action.category,
            params=action.params,
            status=action.status,
        )

    def search(self, query: str, threshold: float = 0.60, max_results: int = 1) -> list[Action]:
        check_embedding_imports()

        if self._embeddings is None:
            self._embeddings = ActionEmbedding().embed_actions(self.actions("valid"))

        # Perform similarity search
        action_embs = self._embeddings

        # Get query embedding
        query_embedding = ActionEmbedding().embed_query(query)

        # Calculate cosine similarities
        similarities: "npt.NDArray[np.float32]" = np.dot(action_embs, query_embedding) / (
            np.linalg.norm(action_embs, axis=1) * np.linalg.norm(query_embedding)
        )

        # Get indices of actions above threshold, sorted by similarity
        valid_indices = np.where(similarities >= threshold)[0]
        sorted_indices = valid_indices[np.argsort(-similarities[valid_indices])]

        # Return up to max_results actions
        result_indices = sorted_indices[:max_results]
        return [self.actions("valid")[i] for i in result_indices]

    def markdown(
        self,
        status: Literal[ActionStatus, "all"] = "valid",
        include_special: bool = True,
        include_description: bool = False,
    ) -> str:
        # Get actions with requested status
        actions_to_format = self.actions(status, include_special=include_special)

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

        actions_str = "\n".join(output)
        if include_description:
            actions_str = f"{self.description}\n{actions_str}"
        return actions_str


@final
class ActionEmbedding:
    _instance: Self | None = None
    _model: "SentenceTransformer | None" = None

    def __new__(cls) -> Self:
        check_embedding_imports()
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._model = SentenceTransformer("all-MiniLM-L6-v2")
        return cls._instance

    def embed_actions(self, actions: list[Action]) -> "npt.NDArray[np.float32]":
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
