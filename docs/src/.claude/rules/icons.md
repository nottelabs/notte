# Icon Mapping

Use consistent icons across all documentation. This mapping ensures visual consistency.

## Platform

| Concept | Icon |
|---------|------|
| Sessions | `tv` |
| Web Agents | `microchip-ai` |
| Functions | `flower` |
| Scraping | `database` |

## Products

| Product | Icon |
|---------|------|
| Agent Builder | `sparkles` |
| Demonstrate Mode | `hand-pointer` |
| Studio | `code` |

## Agent Tools

| Tool | Icon |
|------|------|
| Vaults | `lock` |
| Identities | `fingerprint` |

## Navigation

| Page | Icon |
|------|------|
| Quickstart | `square-arrow-up-right` |
| Concepts | `book` |

## Usage

When adding Cards, links, or navigation items for these concepts, always use the icon from this mapping:

```mdx
<Card title="Sessions" icon="tv" href="/concepts/sessions">
  ...
</Card>
```

## Adding New Icons

If you need to add a new concept:
1. Check Font Awesome first (most reliable in Mintlify)
2. Lucide icons work but not all are supported
3. Update this mapping when adding new icons
4. Keep icons simple and recognizable
