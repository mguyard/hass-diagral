---
name: docs-hass-diagral
description: Writing, updating, and structuring documentation pages for hass-diagral. Covers MDX format, frontmatter, docs.page components, docs.json navigation registration, and when to update docs after code changes.
user-invocable: false
---

# Skill: Documentation — hass-diagral

Use this skill for any task that creates, modifies, or reviews files under `docs/`.

---

## 1. File Format and Location

- All doc files use **MDX** (`.mdx` extension)
- Language: **English**, clear and concise
- Location: `docs/` hierarchy (see §6 for structure)
- Documentation is published with **[docs.page](https://use.docs.page/)** — consult the official docs for the full component catalogue and configuration options

---

## 2. Required Frontmatter

Every `.mdx` file needs at minimum:

```mdx
---
title: Page Title
description: One-sentence description for SEO / nav tooltips
---
```

Pages that are part of a sequence must also include navigation links:

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

Special pages (like FAQ) can use `summary` instead of `description`:

```mdx
---
title: FAQ
summary: Frequently Asked Questions
---
```

---

## 3. MDX Components (docs.page)

> **The list below is non-exhaustive.** docs.page supports many more components.
> Before using a component or checking its props, **look it up via Context7 or a web search** on [use.docs.page](https://use.docs.page/) to get up-to-date documentation.

### 3.1 Callout components (examples)

| Component | Use for |
|-----------|---------|
| `<Info>` | General informational notes |
| `<Warning>` | Important caveats or breaking changes |
| `<Tip>` | Optional best practices / helpful hints |
| `<Success>` | Positive confirmation or completion state |

```mdx
<Info>
All entities refresh every `5 minutes` or upon receiving a [Webhook](/integration/webhook).
</Info>

<Warning>
This action cannot be undone.
</Warning>

<Success>
Setup complete! Check your Home Assistant logs to verify.
</Success>
```

### 3.2 `<Card>` (example)

Used to display structured data examples (e.g. YAML attribute dumps):

```mdx
<Card title="Example of Anomalies Sensor Attributes" icon="newspaper">
```yaml
unit_of_measurement: anomalies
anomalies:
  sensors:
    - serial: '123'
      label: Kitchen Door
```
</Card>
```

### 3.3 `<Accordion>` (example)

Collapsible FAQ-style entries:

```mdx
<Accordion title="How to" icon="question" defaultOpen>
Content shown when expanded.
</Accordion>
```

### 3.4 `<Property>` (example)

Documents an action/service parameter:

```mdx
<Property name="action" type="diagral.arm_groups" required>
Description of what the action does.

  <Accordion title="data" defaultOpen>
    <Property name="group_ids" type="string" required>
      Group(s) to arm. One or many (as array)
    </Property>
  </Accordion>
</Property>
```

### 3.5 `<Steps>` / `<Step>` (example)

Sequential numbered steps (e.g. onboarding guides):

```mdx
<Steps>
  <Step title="Clone this repo">
    ```bash
    git clone https://github.com/mguyard/hass-diagral.git
    ```
  </Step>
  <Step title="Create a new branch">
    ```bash
    git checkout -b new-feature-x
    ```
  </Step>
</Steps>
```

### 3.6 `<Image>` (example)

Displays images hosted remotely or under `docs/images/`:

```mdx
<Image src="/images/configflow-step1.png" alt="Step 1 - Serial ID" />
<Image src="https://example.com/image.png" alt="Description" width="200" />
```

### 3.7 `<Badges>` (example)

Used on the homepage to display GitHub status badges:

```mdx
<Badges>
    <Image src="https://img.shields.io/github/license/mguyard/hass-diagral?style=default&color=0080ff" alt="License" />
</Badges>
```

---

## 4. Code Blocks

Always specify the language:

````mdx
```yaml
```python
```bash
```logs
```json
```mdx
````

To highlight specific lines inside a code block, use `// [!code highlight]` at the end of the line:

```yaml
anomalies: // [!code highlight]
  sensors: // [!code highlight]
    - serial: '123'
```

---

## 5. docs.json — Navigation Registration

When adding a new page, register it in `docs.json` under the correct `tab` and `group`.

### 5.1 Sidebar structure

```json
{
  "group": "Features",
  "tab": "integration",
  "pages": [
    {
      "title": "My New Page",
      "href": "/integration/my-new-page",
      "icon": "microchip"
    }
  ]
}
```

- `tab` must match a tab `id` defined in the `tabs` array
- `href` must match the file path relative to `docs/` (without `.mdx`)
- Icons come from the Font Awesome icon library (e.g. `sitemap`, `envelope`, `terminal`, `cog`, `rocket`)

### 5.2 Existing tabs

| Tab ID | Title | Used for |
|--------|-------|----------|
| `root` | Home | `index.mdx` |
| `integration` | Integration | All integration pages |
| `faq` | FAQ | `faq/index.mdx` |
| `issues` | Issues | `issues/index.mdx` |

### 5.3 Commit type for docs changes

All `docs/` and `docs.json` changes must use:

```
docs(<scope>): 📝 <description>
```

Examples:
- `docs(entities): 📝 Document new battery sensor entity`
- `docs(index): 📝 Update setup requirements section`

---

## 6. Directory Structure

```
docs/
├── index.mdx                   # Homepage (Root tab)
├── docs.json                   # Navigation config (tabs + sidebar)
├── images/                     # All local images referenced in docs
├── integration/
│   ├── index.mdx               # Installation (Getting Started)
│   ├── setup.mdx               # Setup wizard walkthrough
│   ├── entities.mdx            # Entity table + entity-specific details
│   ├── webhook.mdx             # Webhook setup and behavior
│   ├── events.mdx              # DIAGRAL_EVENT structure
│   └── actions.mdx             # Custom service/action reference
├── faq/
│   └── index.mdx               # FAQ (Accordion-based)
├── issues/
│   └── index.mdx               # Known issues
└── misc/
    └── contributing.mdx        # Contribution guide
```

---

## 7. Entity Documentation

Each new entity **must** be added to the table in `docs/integration/entities.mdx`:

```mdx
| Entity Name | Description of what the entity exposes and its unit |
```

---

## 8. When to Update Documentation

After **any code change** (new feature, modified behavior, new entity, changed option, updated service…), apply this process before considering the task complete:

1. **Scan `docs/integration/`** — identify pages that cover the changed area (entities, actions, events, webhook, setup, etc.).
2. **Update only what changed** — add, edit, or remove the relevant sentences, rows, or sections.
3. **Match the existing style** — tone, table format, MDX components, and heading levels must stay consistent with the surrounding content.
4. **When in doubt, ask the developer** — if it is unclear whether documentation needs updating, ask via `vscode_askQuestions` (mandatory — see global rule in `copilot-instructions.md`) before writing or skipping it. Suggested question:

   > "Should I update the documentation for this change? If yes, which page(s)?"
