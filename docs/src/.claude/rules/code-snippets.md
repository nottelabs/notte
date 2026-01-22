# Code Snippets - CRITICAL REQUIREMENT

**ALL code snippets in the documentation MUST be tested and stored in the `snippets/` directory.**

This is enforced by CI/CD and will fail the build if not followed.

## The Rule

Every single code example that appears anywhere in the documentation must:

1. **Live in `snippets/`** - The actual code must be in a file under the `snippets/` directory
2. **Be imported into MDX files** - Documentation pages should import snippets, not contain inline untested code
3. **Be tested** - CI/CD runs tests against all snippets to ensure they work

## Why This Matters

- Untested code examples break user trust
- Stale examples waste developer time
- CI/CD catches broken examples before they reach production

## How to Add Code Examples

### DO: Import from snippets

```mdx
import MyExample from '/snippets/sessions/my_example.mdx';

<MyExample />
```

### DON'T: Write inline code that isn't tested

```mdx
<!-- BAD: This code is not tested and will break -->
```python
some_untested_code()
```
```

## Directory Structure

```
snippets/
├── sessions/           # Session-related examples
├── agents/             # Agent-related examples
├── functions/          # Function-related examples
├── scraping/           # Scraping-related examples
├── workflows/          # Workflow examples
├── browser-controls/   # Browser control examples
└── vaults/             # Vault examples
```

## Before You Commit

1. Check that your snippet exists in `snippets/`
2. Ensure the snippet is importable
3. Run the CI/CD checks locally if possible
4. Never bypass pre-commit hooks

## No Exceptions

There are no exceptions to this rule. If you're adding a code example, it goes in `snippets/` and gets tested. Period.
