# How to use local LLMs (Ollama) to power Notte

## Installing notte in server mode

First you need to install the server version of Notte

```
uv sync --extra server
```

## Installing Ollama
For Mac and Windows, [download Ollama](https://ollama.com/download).

For Linux:
```
curl -fsSL https://ollama.com/install.sh | sh
```

## Downloading models
Ollama has a library of models to choose from, see them [here](https://ollama.com/library).

Before you can use a model, you need to download it (using the name of the model from the library):

```
ollama pull llama3:instruct
```

To view the models you have downloaded and can use:

```
ollama list
```

## Running LiteLLM proxy server

To run LiteLLM with the model you have downloaded, in your terminal:

```
litellm --model ollama/llama3:instruct
```
then you simply need to set the name of the model you want to use inside the notte config object:

## Python code example (notebook)

```python
from notte_agent import Agent
agi = Agent(reasoning_model="ollama/llama3:instruct")
agi.run(task="doom scroll cat memes on google images")
```

notte that there is currently a bug with litellm and ollama which prevents us from using the structured output feature ([issue reference](https://github.com/BerriAI/litellm/issues/8594)).
