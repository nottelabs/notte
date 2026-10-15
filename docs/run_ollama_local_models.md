# Use local models with Notte

Use the local `notte` package when you want to supply your own model. Follow the [local setup](setup.md), then select the Ollama model explicitly with the agent's `reasoning_model` parameter.

Start Ollama and download a model using the [Ollama documentation](https://docs.ollama.com/quickstart). Use the [LiteLLM Ollama integration](https://docs.litellm.ai/docs/providers/ollama) to choose a supported model identifier and configure its endpoint.

Create a local `notte.Session` and pass it to `notte.Agent`, as shown in the repository [README](../README.md#open-source-or-notte-cloud). Supply your Ollama model identifier as `reasoning_model`. Model support for tool use, vision, and structured output varies; verify the capabilities required by your workflow with the model and provider versions you install.
