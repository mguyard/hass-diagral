---
name: docs-hass-diagral
description: Writing, updating, and structuring documentation pages for hass-diagral. Covers MDX format, frontmatter, docs.page components, docs.json navigation registration, and when to update docs after code changes.
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

### 3.7 Badges in a row

docs.page has no `<Badges>` component any more: it renders as "Markdown contains an unknown component". A standalone image, Markdown or `<img>`, renders as a block, and inline `style` is ignored. To put badges side by side, use a one-row table per group, with a blank line between groups — otherwise consecutive tables merge and drop cells:

```mdx
| ![License](https://img.shields.io/github/license/mguyard/hass-diagral) | ![Last Commit](https://img.shields.io/github/last-commit/mguyard/hass-diagral) |
|:---:|:---:|

| ![Stable](https://img.shields.io/github/v/release/mguyard/hass-diagral) | ![Open PRs](https://img.shields.io/github/issues-pr/mguyard/hass-diagral) |
|:---:|:---:|
```

Verified with the local preview on 2026-10-24.

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

To highlight specific lines inside a code block, end the line with `[!code highlight]` written as a comment **in the block's language** — `# [!code highlight]` in YAML, `// [!code highlight]` in JavaScript. With the wrong comment syntax the marker is shown verbatim and nothing is highlighted, which is what `// …` in YAML blocks did on every page until 2026-10-24:

```yaml
anomalies: # [!code highlight]
  sensors: # [!code highlight]
    - serial: '123'
```

### 4.1 docs.page escapes `<`, everywhere, including inside code blocks

docs.page escapes any `<` that cannot open a tag, and its code renderer never decodes the entity back.
The reader sees a literal `&lt;` and copies broken YAML into their automation.
This is not about being inside a `<Warning>` or a `<Card>` — a fenced block at the top level breaks the same way.

The only thing that matters is the character following the `<`:

| Written in the source | Rendered |
|---|---|
| `a <EVENT>` — a letter follows | `a <EVENT>` ✅ |
| `a </x` — a slash follows | `a </x` ✅ |
| `a > 50`, `a >= 50` | unaffected ✅ |
| `a < 50` — a space follows | `a &lt; 50` ❌ |
| `a <50` — a digit follows | `a &lt;50` ❌ |
| `a <= 50` | `a &lt;= 50` ❌ |
| `a &lt; 50` — HTML entity | `a &lt; 50` ❌ |
| `a &#60; 50` — numeric reference | `a &#60; 50` ❌ |

No escape works: not `&lt;`, not `&#60;`, not `\<`.
Four-space indented code blocks are not rendered at all, so they are no way out either.

**Write the comparison so that no bare `<` appears.**
Put the constant first and use `>`, which keeps the meaning exactly:

```yaml
{{ 3 > states('sensor.<alarm>_active_groups') | int(0) }}
```

`|` binds tighter than `>` in Jinja, so this is `3 > (x | int(0))`.
Jinja's `is lt` test also renders correctly, but it is unfamiliar to most Home Assistant users.

Established on the hass-iopool documentation on 2026-08-29, which uses the same docs.page pipeline, with the method in §4.2.
If a future docs.page release fixes it, re-run those cases before relying on `<` again.

### 4.2 Verifying the rendering locally

Never assume a page renders as written — `curl` on a docs.page URL returns the raw MDX, not the DOM, so it proves nothing.
Render the local working tree through the real pipeline instead:

```bash
npx -y @docs.page/cli preview --port 7788 --no-browser
```

It watches the repository root and streams the local files to the hosted renderer.
It prints a preview URL; append the page path after `/preview` to reach a specific page:

```
https://docspage-production.up.railway.app/preview/integration/events?url=ws%3A%2F%2Flocalhost%3A7788
```

Opening it in a normal browser is enough for a visual check.
To assert on the output, drive it with Playwright and read `pre` elements — Chromium blocks the websocket to localhost from a public origin, so the flag is required:

```js
chromium.launch({ args: ['--disable-features=LocalNetworkAccessChecks,PrivateNetworkAccessChecks,BlockInsecurePrivateNetworkRequests'] })
```

Grepping the rendered text for `&lt;` is the check that catches the trap in §4.1.

---

## 5. docs.json — Navigation Registration

When adding a new page, register it in `docs.json`, at the **repository root**, under the correct `tab` and `group`.

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
docs.json                       # Navigation config (tabs + sidebar) — repository root
docs/
├── index.mdx                   # Homepage (Root tab)
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
4. **When in doubt, ask the developer** — if it is unclear whether documentation needs updating, ask with `AskUserQuestion` before writing or skipping it. Suggested question:

   > "Should I update the documentation for this change? If yes, which page(s)?"
