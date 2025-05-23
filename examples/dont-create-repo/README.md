# Don't create repo agent

<img src="https://github.com/user-attachments/assets/113d3db3-6529-49af-ae73-680435e1d559" height=300>

This example shows an Auth Vault Agent that authenticates to github, and then tries to create a repo.
Since we use blocklists, it is not able to, and fails.
Of course in general, you'd rather use blocklists to ensure success, and not failure :).

## Setup

Follow the setup instructions in the [README](../README.md).

## Run the agent

```bash
python agent.py
```
