# notte-llm

LLM integration for Notte, providing LiteLLM-based services for language model interactions.

This package contains:
- LLM engine and service implementations
- Prompt management and templating
- LLM usage tracing and logging
- Structured output support

## Installation

```bash
pip install notte-llm
```

## Usage

```python
from notte_llm.engine import LLMEngine
from notte_llm.service import LLMService

# Create an LLM engine
engine = LLMEngine(model="gpt-4o-mini")

# Create an LLM service
service = LLMService()
```


