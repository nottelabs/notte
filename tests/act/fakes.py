"""A scripted `Decider` for offline `act()` tests."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from notte_core.act import Answer, Answers, DecisionState, Question, WriteContext


def answer(choice: str, keys: list[str], confidence: float = 0.9) -> Answer:
    """`choice` gets most of the probability mass, the other options share the rest."""
    if len(keys) == 1:
        return Answer(choice=choice, probabilities={choice: 1.0}, confidence=confidence)
    rest = 0.1 / (len(keys) - 1)
    return Answer(choice=choice, probabilities={k: 0.9 if k == choice else rest for k in keys}, confidence=confidence)


@dataclass
class FakeDecider:
    """Answers each `choose()` call with the next mapping of question name -> chosen option key.

    Questions without a scripted choice are answered with their first option. `on_choose` runs before
    answering (e.g. to change the page while the "model" thinks).
    """

    choices: list[Mapping[str, str]]
    texts: list[str | None] = field(default_factory=list)
    confidence: float = 0.9
    on_choose: Callable[[], object] | None = None
    states: list[DecisionState] = field(default_factory=list)
    questions: list[dict[str, Question]] = field(default_factory=list)
    contexts: list[WriteContext] = field(default_factory=list)

    async def choose(self, state: DecisionState, questions: Mapping[str, Question]) -> Answers:
        self.states.append(state)
        self.questions.append(dict(questions))
        if self.on_choose is not None:
            result = self.on_choose()
            if hasattr(result, "__await__"):
                await result  # pyright: ignore[reportGeneralTypeIssues]
        script = self.choices.pop(0)
        answers: dict[str, Answer] = {}
        for name, question in questions.items():
            keys = list(question.criteria)
            answers[name] = answer(script.get(name, keys[0]), keys, self.confidence)
        return Answers(answers=answers, model="fake")

    async def write(self, context: WriteContext) -> str | None:
        self.contexts.append(context)
        return self.texts.pop(0)
