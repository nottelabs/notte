# Notte Browser

The browser component of the Notte agentic ecosystem, designed to provide a seamless interface between LLM agents and web browsing capabilities. This package serves as the foundational layer that enables AI agents to interact with web content in a structured and efficient manner.

## Features

- **Browser Management**: Handles browser sessions and windows using Playwright under the hood
- **DOM Processing**: Transforms web pages into structured, agent-friendly formats
- **Error Handling**: Robust error management for various browser-related scenarios
- **Configurable Options**: Flexible configuration for headless mode, user agents, proxies, and more
- **Security Controls**: Built-in web security controls and customizable Chrome arguments

## Core Dependencies

- Python >=3.11
- notte_core
- patchright (Playwright-based browser automation)

## Usage

This package is typically used as part of the larger Notte ecosystem, providing the browser capabilities needed by Notte agents to navigate and interact with web content. It's designed to work seamlessly with other Notte components to enable sophisticated web automation and interaction scenarios.

For more information about the Notte ecosystem, visit [notte.cc](https://notte.cc).
