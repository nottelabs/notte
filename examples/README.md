# How to build an LLM agent with *Notte*

This guide explains how to build a custom LLM agent using *Notte*. The example in `agent.py` demonstrates a basic implementation that you can customize for your specific needs.

## Overview

*Notte* provides a flexible environment for web automation that can be controlled through an API. To build an agent with *Notte*, you need:

1. An agent implementation that coordinates between your LLM and the *Notte* environment
2. A parser that formats *Notte*'s outputs into prompts suitable for your LLM
3. A way to interpret the LLM's responses back into *Notte* commands

## Key Components

### Agent

The `Agent` class in `agent.py` shows how to:
- Initialize a connection to your LLM service
- Manage the conversation flow between the LLM and *Notte*
- Track the state of task completion

### Parser

The parser is crucial for translating between *Notte* and your LLM. You'll need to:

1. Create a custom parser (by extending `BaseNotteParser` or implementing the `Parser` interface)
2. Define how to format:
   - Observations from web pages
   - Available actions
   - Data extraction results
   - Task completion status

The provided `BaseNotteParser` is a simple example that you should modify based on your needs. Consider:
- The prompt format your LLM works best with
- How to structure web observations for your specific tasks
- What action format makes sense for your use case
- How to handle task completion and data extraction

## Example Implementation

See `agent.py` for a basic implementation. Key points to customize:
- The parser implementation
- The prompt engineering in the conversation flow
- How task completion is determined
- Error handling and retry logic

## Best Practices

1. **Custom Parser**: Don't just use the `BaseNotteParser` as-is. Create your own parser that:
   - Formats observations in a way that makes sense for your LLM
   - Structures action possibilities clearly
   - Handles task-specific data extraction

2. **Prompt Engineering**: Carefully design your system prompt and conversation flow

3. **Error Handling**: Add robust error handling for both LLM and *Notte* interactions

4. **Testing**: Test your parser and agent with different scenarios
