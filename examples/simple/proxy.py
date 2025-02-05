# from typing_extensions import override

# from examples.simple.parser import StepAgentOutput
# from notte.common.perception import BasePerception
# from notte.common.proxy import BaseProxy, ProxyObservation
# from notte.env import NotteEnv


# class SimpleProxy(BaseProxy):
#     def __init__(
#         self,
#         env: NotteEnv,
#         perception: BasePerception,
#     ):
#         self.env: NotteEnv = env
#         self.parser: SimpleParser = SimpleParser()
#         self.perception: BasePerception = perception

#     @override
#     async def step(self, data: StepAgentOutput) -> ProxyObservation:
#         params = self.parser.parse(text)
#         if params.output is not None:
#             # we are done => return the output
#             return ProxyObservation(
#                 obs=params.output.answer,
#                 output=params.output,
#                 snapshot=self.env.context.snapshot,
#             )
#         # take a new step in the environment
#         observation = await self.env.raw_step(params.action)
#         return ProxyObservation(
#             obs=self.perception.perceive(observation),
#             output=None,
#             snapshot=self.env.context.snapshot,
#         )
