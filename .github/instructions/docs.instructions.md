---
applyTo: "docs/**"
description: "Use when creating or updating documentation pages in docs/. Covers MDX frontmatter, writing style, docs.page components, navigation registration in docs.json, and entity documentation requirements."
---

# Documentation Guidelines — hass-diagral

## File Format

- All doc files use **MDX** (`.mdx` extension)
- Language: **English**, clear and concise
- Location: `docs/` hierarchy

## Required Frontmatter

Every `.mdx` file needs:

```mdx
---
title: Page Title
description: One-sentence description for SEO / nav tooltips
---
```

Pages that are part of a sequence should also include navigation links:

```mdx
---
title: Page Title
description: ...
previous: /integration/previous-page
previousTitle: Previous Page
next: /integration/next-page
nextTitle: Next Page
---
```

## docs.json — Navigation Registration

When adding a new page, register it under the appropriate section in `docs.json`. The `href` must match the file path relative to `docs/` (without `.mdx`):

```json
{
  "href": "/integration/my-new-page",
  "title": "My New Page"
}
```

All `docs/` and `docs.json` changes must use commit type `docs` with gitmoji 📝.

## Available MDX Components (docs.page)

| Component | Use For |
|-----------|---------|
| `<Info>` | General informational notes |
| `<Warning>` | Important caveats or breaking changes |
| `<Tip>` | Optional best practices / helpful hints |

Example:

```mdx
<Info>
All entities refresh every `5 minutes` or upon receiving a [Webhook](/integration/webhook).
</Info>
```

## Code Blocks

Always specify the language:

```
```yaml
```python
```bash
```mdx
```

## Entity Documentation

Each new entity **must** be added to the table in `docs/integration/entities.mdx`:

```mdx
| Entity Name | Description of what the entity exposes and its unit |
```

## When to Update Documentation

After **any code change** (new feature, modified behavior, new entity, changed option, updated
service…), the documentation must be reviewed and updated as needed:

1. **Scan `docs/integration/`** to find pages that describe the changed area.
2. **Update only what changed** — add, edit, or remove the relevant sentences, rows, or sections.
3. **Match the existing style** — tone, table format, MDX components, and heading levels must
   stay consistent with the surrounding content.
4. **When in doubt, ask** — if it is unclear whether documentation needs updating, ask the
   developer before proceeding:

   > "Should I update the documentation for this change? If yes, which page(s)?"

## Commit Type for Docs

```
docs(<scope>): 📝 <description>
```

Examples:
- `docs(entities): 📝 Document new battery sensor entity`
- `docs(index): 📝 Update setup requirements section`
