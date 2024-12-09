import random
from dataclasses import dataclass, field
from typing import Any, Literal, Self, final

import numpy as np
import numpy.typing as npt
from notte.actions.base import Action
from sentence_transformers import SentenceTransformer


@dataclass
class ActionSpace:
    _actions: list[Action] = field(default_factory=list)
    _embeddings: npt.NDArray[np.float32] | None = None

    def actions(
        self,
        status: list[Literal["valid", "failed", "excluded"]] | None = None,
    ) -> list[Action]:
        if status is None:
            status = ["valid"]
        return [action for action in self._actions if action.status in status]

    def sample(
        self,
        status: list[Literal["valid", "failed", "excluded"]] | None = None,
    ) -> Action:
        action: Action = random.choice(self.actions(status))
        return Action(
            id=action.id,
            description=action.description,
            category=action.category,
            params=action.params,
            status=action.status,
        )

    def search(self, query: str, threshold: float = 0.60, max_results: int = 1) -> list[Action]:
        if self._embeddings is None:
            self._embeddings = ActionEmbedding().embed_actions(self.actions(["valid"]))

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
        return [self.actions(["valid", "failed", "excluded"])[i] for i in result_indices]

    def markdown(
        self,
        status: Literal["valid", "failed", "excluded"],
    ) -> str:
        # Get actions with requested status
        actions_to_format = self.actions([status])

        # Group actions by category
        grouped_actions: dict[str, list[Action]] = {}
        for action in actions_to_format:
            if action.category is None:
                raise ValueError("Action has no category")
            if action.category not in grouped_actions:
                grouped_actions[action.category] = []
            grouped_actions[action.category].append(action)

        # Build markdown output
        output = []
        for category, actions in grouped_actions.items():
            output.append(f"\n# {category}")
            for action in actions:
                line = f"* {action.id}: {action.description}"
                if action.params is not None and len(action.params) > 0:
                    line += f" ({action.params})"
                output.append(line)

        return "\n".join(output)

    @staticmethod
    def from_json(json: dict[str, Any]) -> "ActionSpace":
        return ActionSpace(
            _actions=[Action.from_json(action) for action in json["actions"]],
            _embeddings=json["embeddings"],
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
