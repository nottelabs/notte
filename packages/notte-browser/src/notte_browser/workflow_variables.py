from typing import Any

import chevron
from notte_agent.common.types import AgentResponse
from notte_core.agent_types import AgentCompletion
from notte_core.llms.engine import LLMEngine
from notte_sdk.types import AgentRunRequest
from pydantic import BaseModel
from typing_extensions import override


class Workflow(BaseModel):
    request: AgentRunRequest
    variables_format: type[BaseModel] | None
    steps: list[AgentCompletion]

    @staticmethod
    async def from_response(
        request: AgentRunRequest, response: AgentResponse, variables_format: type[BaseModel] | None = None
    ) -> "Workflow":
        workflow = Workflow(
            request=request,
            variables_format=variables_format,
            steps=[step for step in response.trajectory if isinstance(step, AgentCompletion)],
        )
        if variables_format is not None:
            return await WorkflowVariablesPipe.forward(workflow)
        return workflow

    def fill(self, variables: dict[str, Any] | None = None) -> "Workflow":
        if variables is None:
            return self
        for step in self.steps:
            value = getattr(step.action, "value", None)
            if value is not None and value in variables.keys():
                step.action.value = variables[value]
        return self


class Variables(BaseModel):
    search_query: str


class VariableIdentifier(BaseModel):
    is_variable: bool
    justification: str
    variable_name: str | None = None

    @override
    def model_post_init(cls, __context: Any) -> None:
        if cls.is_variable and cls.variable_name is None:
            raise ValueError("variable_name is required when is_variable is True")


class VariableIdentifierList(BaseModel):
    steps: list[VariableIdentifier]

    @staticmethod
    def example() -> "VariableIdentifierList":
        return VariableIdentifierList(
            steps=[
                VariableIdentifier(
                    is_variable=False,
                    justification=(
                        "This action is a click action to nagitave to the contact page. "
                        "This is not a variable but a constant step of the workflow"
                    ),
                    variable_name=None,
                ),
                VariableIdentifier(
                    is_variable=True,
                    justification="The user reference a 'date' field in the provided variables and this action fill a date input format",
                    variable_name="date",
                ),
            ]
        )


prompt = """
You are an expert at identifying variables in a web automation workflow.

You will be given a specific instance of a workflow through sequetial actions.

{{steps}}

The steps were generated for this specific task:

{{task}}

You goal is to analyse the steps and identify the variables that are used in the steps to make the workflow generic.

Here are the variables that you should pay attention to:

{{variables}}

Now, for each step in the workflow, run a separate analysis to fill out the following JSON schema:

{{variables_format}}

Here is an example of the expected output:

```json
{{example}}
```
Please return the respect the given JSON schema. Your turn:
"""


class WorkflowVariablesPipe:
    @staticmethod
    async def forward(workflow: Workflow) -> Workflow:
        if workflow.variables_format is None:
            return workflow

        engine = LLMEngine()
        variables = await engine.structured_completion(
            messages=[
                {
                    "role": "user",
                    "content": chevron.render(
                        template=prompt,
                        data={
                            "steps": [step.model_dump(exclude={"obs"}) for step in workflow.steps],
                            "task": workflow.request.task,
                            "variables": workflow.variables_format.model_json_schema(),
                            "example": VariableIdentifierList.example(),
                        },
                    ),
                }
            ],
            response_format=VariableIdentifierList,
        )
        assert len(variables.steps) == len(workflow.steps)
        for step, var in zip(workflow.steps, variables.steps):
            if var.is_variable:
                step.action.value = f"{{{var.variable_name}}}"
        return workflow
