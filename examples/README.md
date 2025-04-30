# How to run the examples

## Setup

The setup is the same for all the examples.

```bash
cd <example-folder>
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then fill up the `.env` file with your own credentials.

Note that some of the examples require a 2FA token. For the GitHub websites, you can get it from the [2FA section of your Github account settings](https://github.com/settings/security). For other websites, you can directly get it from any of the 2FA apps installed on your phone (click on the corresponding app and then on "Show token").

> If necessary, you can use a package like `pyotp` to get the current 2FA code, to validate the secret.


## Run the agent

```bash
python agent.py
```
