# Naming Conventions

## NotteClient Instance

When instantiating the `NotteClient`, **always** name the variable `client`, not `notte`.

### DO

```python
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # ...
```

### DON'T

```python
from notte_sdk import NotteClient

notte = NotteClient()  # Wrong - don't use "notte"

with notte.Session() as session:
    # ...
```

## Why

- Consistency across all documentation and examples
- `client` is the standard convention for SDK client instances
- Avoids confusion between the product name and variable names
