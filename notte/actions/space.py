import random
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Self, final

import numpy as np
import numpy.typing as npt
from sentence_transformers import SentenceTransformer

from notte.actions.base import (
    Action,
    ActionRole,
    ActionStatus,
    PossibleAction,
    SpecialAction,
)


class SpaceCategory(Enum):
    HOMEPAGE = "homepage"
    SEARCH_RESULTS = "search-results"
    DATA_FEED = "data-feed"
    ITEM = "item"
    AUTH = "auth"
    FORM = "form"
    MANAGE_COOKIES = "manage-cookies"
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
    _embeddings: npt.NDArray[np.float32] | None = None

    def __post_init__(self):
        # check no special actions are present
        if any(SpecialAction.is_special(action.id) for action in self._actions):
            action_ids = [action.id for action in self._actions]
            raise ValueError(f"Special actions are not allowed in the action space: {action_ids}")

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
        if self._embeddings is None:
            self._embeddings = ActionEmbedding().embed_actions(self.actions("valid"))

        # Perform similarity search
        action_embs = self._embeddings

        # Get query embedding
        query_embedding = ActionEmbedding().embed_query(query)

        # Calculate cosine similarities
        similarities: npt.NDArray[np.float32] = np.dot(action_embs, query_embedding) / (
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
                raise ValueError("Action has no category")
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

    @staticmethod
    def from_json(json: dict[str, Any]) -> "ActionSpace":
        return ActionSpace(
            description=json["description"],
            _actions=[Action.from_json(action) for action in json["actions"]],
            _embeddings=json["embeddings"],
            category=SpaceCategory(json["category"]),
        )


@final
class ActionEmbedding:
    _instance: Self | None = None
    _model: SentenceTransformer  # type: ignore

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._model = SentenceTransformer("all-MiniLM-L6-v2")
        return cls._instance

    def embed_actions(self, actions: list[Action]) -> npt.NDArray[np.float32]:
        descriptions = [action.embedding_description() for action in actions]
        return self._model.encode(descriptions, convert_to_numpy=True)

    def embed_query(self, query: str) -> npt.NDArray[np.float32]:
        return self._model.encode(query, convert_to_numpy=True)
