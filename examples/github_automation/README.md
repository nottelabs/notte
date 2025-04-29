# Github Issue Agent

## Description

This is an example of an agent that can be used to create issues in a Github repository.
The

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install notte==1.4.3 pandas==2.2.3 halo==0.0.31
```

```bash
cp .env.example .env
```

Edit the `.env` file with your own credentials.
## Getting the MFA secret token
For the connection to work reliably, we need access to a 2FA token. Here's how you access / generate it:

[token.webm](https://github.com/user-attachments/assets/5052df2a-bbb1-4133-b321-2f29653cf910)

If necessary, you can use a package like `pyotp` to get the current 2FA code, to validate the secret.

## Update the issue template
The issue template is in `prompts.py`. If you don't update it, it will create an issue with a generic title and description.

## Run the agent

```bash
python agent.py
```
