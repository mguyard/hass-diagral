# GitHub Copilot Custom Instructions for `hass-diagral`

## Project Context

- **Project Type:**  
  This repository is a **custom integration for [Home Assistant](https://www.home-assistant.io/)**, written in Python.
- **Purpose:**  
  The integration connects Home Assistant to the Diagral alarm system, exposing alarm states, sensors, and diagnostics, and providing Home Assistant entities, events, and configuration flows.
- **Structure:**  
  - All integration code is in `custom_components/diagral/`.
  - Documentation is in the `docs/` directory and `docs.json`.
  - The integration uses Home Assistant's config flow, entity platforms (sensor, alarm_control_panel, etc.), and DataUpdateCoordinator pattern.
  - The codebase follows Home Assistant's best practices for custom components.
- **Language:**  
  - All code, comments, and docstrings must be in **English** (even though the maintainer is French).
- **Documentation:**  
  - All files in `docs/` and `docs.json` are documentation and must use the `docs` commit type.
  - Documentation is in Markdown or MDX, and must be clear and concise.
- **Testing:**  
  - Use `pytest` conventions for tests (if/when present).
  - Place tests in a `tests/` directory.
  - **Always suggest adding or updating tests when new features or bug fixes are implemented.**
- **Linting/Formatting:**  
  - Use `flake8` as the linter, with a maximum line length of 150 characters (see `.vscode/settings.json`).
  - You may also use `black` for formatting if desired, but `flake8` is required for linting.

## External Context and Libraries

- You may use context7 for code generation and suggestions.
- You are allowed to use libraries and APIs from:
  - `/home-assistant/core`
  - [developers.home-assistant.io](https://developers.home-assistant.io)
- Use these resources to ensure compatibility and best practices with Home Assistant integrations.

## Pull Request Best Practices

- **Title:**
  - The PR title MUST follow the same format as the commit message guidelines (see below):
    `<type>[optional scope]: <gitmoji> <description>`
  - The title should summarize the main purpose of the PR.

- **Description:**
  - The PR description MUST provide a clear summary of all changes included in the PR.
  - List and briefly explain each commit included in the PR.
  - For each commit, include a direct link to the commit (e.g., `https://github.com/mguyard/hass-diagral/commit/<sha>`).
  - If the PR addresses or closes issues, reference them using GitHub keywords (e.g., `Closes #123`).
  - Use bullet points for clarity if needed.

- **Branch:**
  - All PRs MUST use `dev` as the base branch.

- **General:**
  - Ensure your PR is focused and does not mix unrelated changes.
  - Follow all other project and commit message guidelines described above.


## Commit Message Guidelines

- **Format:**  
  ```
  <type>[optional scope]: <gitmoji> <description>

  [optional body]
  ```
- **Types and Gitmoji:**  
  Use the following gitmoji for each commit type to ensure consistency:
  - `feat`: ✨ (sparkles) — For new features
  - `fix`: 🐛 (bug) — For bug fixes
  - `docs`: 📝 (memo) — For documentation changes (including anything in `docs/` or `docs.json`)
  - `refactor`: ♻️ (recycle) — For code refactoring that does not add features or fix bugs
  - `test`: ✅ (white check mark) — For adding or updating tests
  - `chore`: 🔧 (wrench) — For maintenance, build, or tooling changes

- **Examples:**
  ```
  feat(alarm_control_panel): ✨ Add support for partial arming mode

  * Implements `partial` arming for Diagral alarm.
  * Updates UI to reflect new mode.
  ```

  ```
  docs(readme): 📝 Update README with troubleshooting section

  * Adds common issues and solutions for Diagral integration.
  ```

  ```
  fix(sensor): 🐛 Fix humidity sensor value conversion
  ```

  ```
  refactor(coordinator): ♻️ Refactor update logic for better reliability
  ```

  ```
  test(alarm_control_panel): ✅ Add tests for alarm state transitions
  ```

  ```
  chore(deps): 🔧 Bump minimum Home Assistant version to 2024.6.0
  ```

- **Rules:**
  - Limit the first line to 72 characters or less.
  - Use backticks for code/entity references in the description.
  - Write the body in bullet points for clarity if needed.
  - Always write commit messages in English.

## Python-Specific Best Practices

- Use virtual environments for development.
- Use `async`/`await` for I/O-bound operations.
- Handle exceptions gracefully and log errors.
- Use `logging` instead of `print` for output.
- Prefer list comprehensions and generator expressions for concise code.
- Avoid global variables.
- Use constants for configuration values.

## Home Assistant Integration

- Follow [Home Assistant custom component guidelines](https://developers.home-assistant.io/docs/creating_component_index/).
- Entities should have unique IDs and meaningful names.
- Use translations for entity names and options.
- Ensure all entities are documented in `docs/integration/entities.mdx`.

## For Copilot Coding Agent

- When asked to create or modify files, always use English for code, comments, and docstrings.
- When generating documentation, use Markdown or MDX and English.
- When generating commit messages, follow the Conventional Commits and gitmoji rules above.
- When working with Home Assistant, prefer async APIs and follow the entity/component patterns in the codebase.
- All configuration, code, and documentation must be consistent with the existing project structure and standards.
- **Always suggest adding or updating tests for new features or bug fixes.**
- **Enforce flake8 linting with a max line length of 150 characters.**

---

These instructions are designed to help GitHub Copilot and Copilot Coding Agent generate code, documentation, and commit messages that are consistent with the project's standards and best practices.
