# Start Bitwarden

```bash
docker compose up -d
```

# First time setup

Go to [text](http://localhost:8080) and set up an  account.

# Get API key

Go to [text](http://localhost:8080/#/settings/security/security-keys) and create a new API key.

# Add API key to .env

```bash
echo "BITWARDEN_API_KEY=your_api_key" >> .env
```

