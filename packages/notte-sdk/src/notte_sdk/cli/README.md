# Notte Workflow CLI

Manage Notte workflow lifecycle from the command line.

## Usage

```bash
notte workflow [--workflow-path FILE] COMMAND [OPTIONS]
```

## Commands

### Create
```bash
notte workflow --workflow-path my_workflow.py create
```

### Update
```bash
notte workflow --workflow-path my_workflow.py update
```

### Run
```bash
# Run locally
notte workflow --workflow-path my_workflow.py run --local

# Run on cloud
notte workflow --workflow-path my_workflow.py run --variables vars.json
```

### Benchmark
```bash
# Run 10 iterations locally
notte workflow --workflow-path my_workflow.py benchmark --local --iterations 10

# Run on cloud with parallelism
notte workflow --workflow-path my_workflow.py benchmark --iterations 50 --parallelism 4
```

## Auto-Detection

When running from a workflow file, `--workflow-path` is optional:

```python
# my_workflow.py
from notte_sdk import NotteClient, workflow_cli

def run(url: str) -> str:
    # ... workflow code ...
    return result

if __name__ == "__main__":
    workflow_cli()  # Enables CLI commands
```

```bash
# These work without --workflow-path
python my_workflow.py create
python my_workflow.py run --local
python my_workflow.py benchmark --iterations 10
```

## Environment Variables

- `NOTTE_API_KEY` - API key (required for cloud operations)
- `NOTTE_API_URL` - API server URL (optional)

