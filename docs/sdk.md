# Notte Python SDK

## Setup

### Installation

Install notte SDK using

```bash
pip install notte
```

### Authentication

To use the Notte SDK, you'll need an API key. You can create one at [web.notte.cc](https://web.notte.cc).

Set your API key either through environment variables:

```bash
export NOTTE_API_KEY="your-api-key"
```
or directly inside the the `NotteClient`:
```python
client = NotteClient(api_key="your-api-key")
```


## Key Features

- **Managed Sessions**: Reliable browser automation in the cloud
- **Smart Caching**: Optimized for speed and cost
- **Simple API**: Direct mapping to Notte's core environment

## Core Methods

- `observe(url)`: Navigate and analyze page
- `step(action_id, params)`: Execute action
- `scrape()`: Extract structured data

For example you can start a session and navigate to a page:

```python
from notte.sdk import NotteClient
url = "https://www.google.com/flights"
with NotteClient() as client:
    # Navigate to the page and observe its state
    obs = client.observe(url=url)
    # Interact with the page - type "Paris" into input field I1
    obs = client.step(action_id="I1", params="Paris")
    # Print the current state of the page
print(obs.space.markdown())
```
You can also start and close sessions your selves using

```python
client = NotteClient()
# start session with timeout of 3 minutes
client.start(timeout=3)
...
client.close()
```

but remember to close sessions when you are done otherwise you will be charged for the session until timeout.

you can also make a single request with auto start/close

```python
client = NotteClient()
obs = client.scrape(url=url)
```


## Documentation

Full documentation available at [docs.notte.cc](https://docs.notte.cc)
