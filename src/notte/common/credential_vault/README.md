## Basic example code

```python
from examples.pipistrello.agent import PipistrelloAgent as Agent, PipistrelloAgentConfig as AgentConfig
from notte.common.credentials.HashiCorp.vault import HashiCorpVault
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize vault with environment variables
vault = HashiCorpVault(
    url=os.getenv("VAULT_URL"),
    token=os.getenv("VAULT_DEV_ROOT_TOKEN_ID")
)

# Add credentials from environment variables
vault.add_credentials(
    url="https://x.com",
    username=os.getenv("TWITTER_USERNAME"),
    password=os.getenv("TWITTER_PASSWORD")
)

# Configure and initialize agent with vault
config = AgentConfig().cerebras().dev_mode()
config.env.disable_web_security().not_headless().cerebras().steps(15)
agent = Agent(config=config, vault=vault)
```
