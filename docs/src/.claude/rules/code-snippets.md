# sniptest

Tool for generating tested code snippets for Mintlify docs.

## How It Works

1. Write testable Python in `/testers/*.py` with `# @sniptest` comments
2. Pre-commit hook runs `python sniptest/generate.py`
3. Generated `.mdx` files appear in `/snippets/`
4. Docs import from `/snippets/` - never write inline code blocks
5. CI/CD tests all `/testers/*.py` for validity

## Syntax

```python
# @sniptest filename=example.py
# @sniptest highlight=3-5,8
# @sniptest show=1-15

from notte_sdk import NotteClient

client = NotteClient()
# code here...

# Hidden below (via show=1-15)
if __name__ == "__main__":
    test()
```

## Decorators

| Decorator | Example | Output |
|-----------|---------|--------|
| `filename` | `filename=example.py` | Filename in header |
| `highlight` | `highlight=1-2,5` | `highlight={1-2,5}` |
| `focus` | `focus=2,4-5` | `focus={2,4-5}` |
| `lines` | `lines=true` | Show line numbers |
| `expandable` | `expandable=true` | Collapsible block |
| `wrap` | `wrap=true` | Wrap long lines |
| `icon` | `icon=rocket` | `icon="rocket"` |
| `show` | `show=5` or `show=5-20` | Pre-shave lines (single = that line only) |

### Line Number Syntax

| Type | Example | Means |
|------|---------|-------|
| Single | `5` | Line 5 |
| Range | `1-5` | Lines 1 through 5 |
| Mixed | `1-2,5,8-10` | Lines 1, 2, 5, 8, 9, 10 |

Works for `highlight` and `focus`. The `show` decorator only supports single range or single number.

### Processing Order

All line numbers refer to the **original code** (after `# @sniptest` comments are stripped).

`show` shaves lines AND remaps `highlight`/`focus` to match:

```
# @sniptest show=3-5
# @sniptest highlight=4-5

Original:        Output:
1: line1         (removed)
2: line2         (removed)
3: line3    →    1: line3
4: line4    →    2: line4  ← highlighted
5: line5    →    3: line5  ← highlighted

Result: highlight={2-3}
```

Lines outside `show` range are removed from `highlight`/`focus`.

## Commands

```bash
python sniptest/generate.py           # Generate all
python sniptest/generate.py --dry-run # Preview
python sniptest/generate.py --clean   # Remove orphans
python sniptest/generate.py --verbose # Show unchanged
```

## Generated Header

```mdx
{/* Auto-generated mdx file. Do not edit! */}
{/* @sniptest testers/agents/example.py */}
```

## Using in Docs

```mdx
import Example from '/snippets/agents/example.mdx';

<Example />
```

## No Inline Code

Never write code blocks directly in MDX. Always import from `/snippets/`.
