## Basic example code

```python
from notte_agent.main import Agent
from notte_integrations.credentials.hashicorp.vault import HashiCorpVault
import os
from dotenv import load_dotenv


# CRITICAL: make sure to start the vault server before running the agent
# > cd packages/notte-integrations/src/notte_integrations/credentials/hashicorp
# > docker-compose --env-file ../../../../../.env up

# Then, set the VAULT_URL environment variable either to .env file or

# VAULT_URL=http://0.0.0.0:8200
# VAULT_DEV_ROOT_TOKEN_ID=<your-vault-dev-root-token-id>

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
agent = Agent(vault=vault)
```
