"""Client for decision models (e.g. TypeSafe Jev).

Decision models are not chat models: they take a `state` and a set of typed `questions`
and return typed answers with probabilities instead of generated text. They are served by
OpenRouter on a dedicated endpoint, which litellm does not support, hence this small client.
"""

import os
from typing import Annotated, Any, Literal

import httpx
from notte_core.common.logging import logger
from notte_core.errors.base import NotteBaseError
from pydantic import BaseModel, Field, TypeAdapter

DEFAULT_DECISION_MODEL = "~typesafe/jev-latest"
OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
# maximum number of options for a single choice question
MAX_CHOICE_OPTIONS = 255


class DecisionModelError(NotteBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(
            dev_message=f"Decision model request failed: {message}",
            user_message="The decision model failed to answer.",
            agent_message=None,
            should_retry_later=True,
        )


class ChoiceQuestion(BaseModel):
    """Pick exactly one option out of `criteria` (option name -> option description)."""

    type: Literal["choice"] = "choice"
    instructions: str
    criteria: dict[str, str] = Field(min_length=2, max_length=MAX_CHOICE_OPTIONS)


class NoulQuestion(BaseModel):
    """Probability that a statement is true."""

    type: Literal["noul"] = "noul"
    instructions: str


DecisionQuestion = ChoiceQuestion | NoulQuestion


class ChoiceAnswer(BaseModel):
    type: Literal["choice"] = "choice"
    choice: str
    probabilities: dict[str, float]
    confidence: float

    def top(self, k: int = 3) -> list[tuple[str, float]]:
        return sorted(self.probabilities.items(), key=lambda item: -item[1])[:k]


class NoulAnswer(BaseModel):
    type: Literal["noul"] = "noul"
    noul: float


DecisionAnswer = Annotated[ChoiceAnswer | NoulAnswer, Field(discriminator="type")]
_ANSWERS_ADAPTER: TypeAdapter[dict[str, DecisionAnswer]] = TypeAdapter(dict[str, DecisionAnswer])


class DecisionUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0


class DecisionResponse(BaseModel):
    model: str
    answers: dict[str, DecisionAnswer]
    usage: DecisionUsage = Field(default_factory=DecisionUsage)

    def choice(self, question_id: str) -> ChoiceAnswer:
        answer = self.answers[question_id]
        if not isinstance(answer, ChoiceAnswer):
            raise DecisionModelError(f"expected a choice answer for '{question_id}' but got '{answer.type}'")
        return answer

    def noul(self, question_id: str) -> float:
        answer = self.answers[question_id]
        if not isinstance(answer, NoulAnswer):
            raise DecisionModelError(f"expected a noul answer for '{question_id}' but got '{answer.type}'")
        return answer.noul


class DecisionEngine:
    def __init__(
        self,
        model: str = DEFAULT_DECISION_MODEL,
        api_key: str | None = None,
        base_url: str = OPENROUTER_DECISIONS_URL,
        timeout: float = 30.0,
    ):
        self.model: str = model
        self.base_url: str = base_url
        self.timeout: float = timeout
        self._api_key: str | None = api_key or os.getenv("OPENROUTER_API_KEY")
        if self._api_key is None:
            raise ValueError("OPENROUTER_API_KEY is required to use decision models")
        self.usage: DecisionUsage = DecisionUsage()
        self.nb_calls: int = 0

    async def decide(
        self,
        state: str | dict[str, Any] | list[Any],
        questions: dict[str, DecisionQuestion],
    ) -> DecisionResponse:
        """Ask all `questions` about `state` in a single call (questions are evaluated independently)."""
        payload = {
            "model": self.model,
            "state": state,
            "questions": {qid: question.model_dump() for qid, question in questions.items()},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                http_response = await client.post(
                    self.base_url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.HTTPError as e:
            raise DecisionModelError(f"{type(e).__name__}: {e}") from e
        if http_response.status_code != 200:
            raise DecisionModelError(f"HTTP {http_response.status_code}: {http_response.text[:500]}")
        data = http_response.json()
        if "answers" not in data:
            raise DecisionModelError(f"unexpected response: {str(data)[:500]}")

        response = DecisionResponse(
            model=data.get("model", self.model),
            answers=_ANSWERS_ADAPTER.validate_python(data["answers"]),
            usage=DecisionUsage.model_validate(data.get("usage") or {}),
        )
        missing = set(questions) - set(response.answers)
        if len(missing) > 0:
            raise DecisionModelError(f"missing answers for questions: {sorted(missing)}")

        self.nb_calls += 1
        self.usage = DecisionUsage(
            input_tokens=self.usage.input_tokens + response.usage.input_tokens,
            output_tokens=self.usage.output_tokens + response.usage.output_tokens,
            cost=self.usage.cost + response.usage.cost,
        )
        logger.trace(f"🎲 decision model usage: {response.usage}")
        return response
