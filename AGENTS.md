# Repository Guidelines

Keep this file entirely in English, including headings, examples, and future additions. This does not change the language requirements for product UI, documentation, or release notes.

## Project Structure & Module Organization

- `backend/app/`: FastAPI application factory (`main.py`), configuration schema (`config.py`), private persisted settings (`runtime_settings.py`), web adapters, and read-only campus API/authentication (`campus.py`, `campus_auth.py`).
- `frontend/src/`: React/TypeScript interface and CSS; keep UI assets here. `frontend/vite.config.ts` configures the `/api` development proxy.
- `tests/`: backend and adapter tests using synthetic responses.
- `scripts/`: dependency installation, development server supervision, and live-search checks.
- `skills/ask-danta-research/`: repository-owned research Skill, loaded by `backend/app/research.py` and applied in the Agent.
- `plan.md`: milestones. Update it and `README.md` when behavior changes; distinguish implemented features from plans.

## Build, Test, and Development Commands

Use Python 3.11+, uv, and Node.js 22.12+ with npm. Run from the repository root:

- `python scripts/setup.py`: install locked dependencies; configure services through the Settings UI.
- `python scripts/dev.py`: start frontend and backend on loopback; Ctrl+C stops both.
- `uv run --frozen pytest -q`: run isolated backend tests.
- `npm --prefix frontend run build`: check TypeScript and build frontend assets.
- `python scripts/dev.py --smoke`: start, verify, and stop both servers; stop existing development servers first.
- `python scripts/check_search.py`: validate actual Tavily search against a running backend; requires live configuration and consumes service quota.
- `uv run --frozen python scripts/campus_login.py`: interactive project-owned campus login; passwords must never appear in command arguments or chat.
- `uv run --frozen python scripts/check_campus.py`: validate campus search and thread contracts directly, without starting the backend; requires project-owned credentials and reads real posts.
- `uv run --frozen python scripts/check_research_chat.py`: validate the live cross-source Agent tool chain and web-only followup; requires a running stage-four backend and consumes model/search quota.

## UI Design and Local Release

- Use the ChatGPT web and desktop interfaces as the primary references for layout, interaction, and visual hierarchy, while retaining this project's branding and Chinese UI copy.
- After each completed change, run `npm run desktop:dist` locally and write build artifacts to `release/`. If a running application locks existing files, use a separate subdirectory under `release/`. Report the actual output path and validation results when delivering the change.

## Coding Style & Naming Conventions

Use four-space Python indentation, `snake_case` functions/modules, and `PascalCase` classes. Add type annotations to new interfaces and validate external data with Pydantic.

Use two-space TypeScript indentation, single-quoted strings, semicolons, `PascalCase` components/types, and `camelCase` functions/state. Preserve Chinese UI copy. No formatter or linter is configured; follow surrounding code and avoid unrelated reformatting.

## Chinese Documentation and Copywriting

These rules apply to the README, project documentation, Chinese PR descriptions, release notes, UI explanations, and demo copy. Use formal, direct, natural modern Chinese by default; commit messages follow the English convention below. Explicit user requests take precedence over the default writing style.

### Content and Tone

- Lead with the project's purpose, actual behavior, or operation result, then provide necessary conditions and limitations. Use concrete nouns and verbs; avoid stacked adjectives, bureaucratic language, and conversational openings.
- Make every sentence informative. Remove empty slogans, praise, padding, and repetitive summaries. Do not substitute phrases such as "empower," "ultimate experience," or "one-stop solution" for feature descriptions. Avoid unnecessary transitions such as "it is worth noting" or "in conclusion."
- State facts directly. Do not invent contrasts such as "not X, but Y" or "not only ... but also ..." to elevate the tone. Preserve real distinctions, negations, and limitations; these constructions are not mechanically banned.
- Preserve conditions, scope, attribution, and certainty. Distinguish implemented features, plans, simulated demos, and actual validation. Do not turn "supports source citations" into "guarantees accurate answers." Never invent data, testimonials, performance conclusions, or personal experiences to make copy more concrete.
- Formal writing need not be verbose, and natural writing need not be colloquial. Do not force exclamations, rhetorical questions, jokes, or personification. Do not sacrifice meaning or paragraph flow merely to shorten sentences.

### Structure and Formatting

- Write the README for first-time readers: explain purpose, main features, deployment and configuration, usage boundaries, and essential development entry points. Avoid promotional copy, conversational replies, and development diaries. Put milestone progress and verification records in `plan.md`; link to separate documents for detailed topics.
- Use descriptive headings such as "Deployment and Configuration" or "Data Management and Usage Boundaries." Prefer connected paragraphs, lists for parallel information, numbered steps for procedures, and tables for parameter or option comparisons. Do not force three-point lists, excessive subheadings, or repeated summaries for visual symmetry.
- Use Chinese punctuation in Chinese prose. Insert one ASCII space between Chinese text and English words or Arabic numerals, but no space between English words or numerals and Chinese punctuation. Preserve official spellings of proper names and use terminology consistently.
- Preserve commands, identifiers, paths, URLs, and configuration values exactly. Do not change case, quotes, or spacing while polishing prose. Check affected anchors after renaming headings; use descriptive link labels instead of "click here."

### Demos and Promotional Materials

- Show the product through its actual interface and operation by default. Opening and closing frames may retain the project name and logo. Unless explicitly requested, do not add slogans, voiceovers, explanatory captions, or closing calls to action.
- Preserve necessary status and data labels within the interface. Explain the nature and limitations of demo data in the README's demo description; do not overlay repetitive promotional text.
- When additional copy is needed, describe only features observable on screen. Do not evaluate the experience on the user's behalf or add abstract claims such as "Every step is visible."

The following examples illustrate the intended style; use the suggested wording only when the corresponding feature is implemented:

| Avoid | Prefer |
| --- | --- |
| Campus questions, backed by evidence. | Search public web pages and campus posts with source citations. |
| Every step is visible. | The interface displays tool status and elapsed time. |
| Effortlessly begin your intelligent campus journey. | Run `python scripts/dev.py` to start the services. |

Before committing, check facts, commands, defaults, paths, and links. Remove repetition and ensure editing has not expanded feature promises. Wording-only documentation changes do not require application tests. For operational instructions, verify the corresponding implementation or commands.

References: [Humanizer-zh](https://github.com/op7418/Humanizer-zh/blob/main/SKILL.md), a Chinese editing skill, and [Chinese Technical Documentation Style Guide](https://github.com/ruanyf/document-style-guide). Apply only guidance relevant to this project. Do not automatically install external skills or copy fixed sentence lengths or rewriting templates. Actual project requirements and user instructions take precedence.

## Testing Guidelines

Use pytest, FastAPI `TestClient`, and HTTPX `MockTransport`. Name files `test_*.py` and functions `test_*`. Tests must ignore local credentials and avoid external requests. Cover changed behavior, validation, upstream failures, and secret redaction. No numerical coverage threshold is configured. Record live verification separately from mocked tests; check desktop and narrow layouts for UI changes.

## Commit, Pull Request & Release Guidelines

### Commit Convention

Write commit messages in English using this format:

```text
<type>(<scope>): <summary>
```

- Use types such as `feat`, `fix`, `docs`, `refactor`, `test`, `build`, `ci`, or `chore`.
- Scope is optional; use stable module names such as `auth`, `posts`, or `search`. Keep the summary short, specific, and imperative, without a trailing period.
- When details are needed, leave a blank line after the subject and write the body as unordered list items beginning with `- `. Omit the body for simple commits.
- Keep commits atomic. Do not mix unrelated formatting, dependency, or version changes, or merge temporary commits such as `WIP` or `fixup!`.
- Commit promptly after each small, coherent change is complete and its relevant checks pass. Do not wait until the entire task or milestone is finished, or for a separate user reminder; keep each commit independently reviewable.
- For breaking changes, use `<type>(<scope>)!: <summary>` (or `<type>!: <summary>` without a scope) and include a `BREAKING CHANGE:` footer explaining the impact and migration steps.

### Pull Requests

Write PR descriptions for reviewers who did not participate in development, explaining the current diff. Write release notes for users of that version, explaining available features, installation, and upgrades. Author them separately; do not paste commit lists or chat transcripts into either.

- Summarize the final change and its purpose in the title. Lead the body with the concrete problem and resulting behavior. Use triggers or before-and-after examples when helpful; avoid unverifiable summaries such as "improve the experience" or "enhance functionality."
- Scale the explanation of scope, implementation rationale, validation, and limitations to the change. Simple changes may need only one or two paragraphs and validation details. Use sections for complex changes without forcing a fixed template.
- Include only technical details that help review. Omit development diaries, abandoned approaches, and repair history unrelated to the final diff; include history only when it explains a meaningful tradeoff. Update the title and body when scope changes.
- Report checks actually performed and their results. Distinguish automated tests, mocked responses, live-service integration, and manual validation. Do not present a successful build as comprehensive functional acceptance. Explain any material validation gaps accurately.
- Link relevant issues or plan items, and include sanitized screenshots for UI changes. Explain affected users and migration steps for breaking changes. Never invent issues, test results, or performance measurements.

### Release Notes

- Describe the corresponding tag and distributed packages. Do not present working-tree, main-branch, or planned features as released. Introduce core capabilities in an initial release; emphasize changes since the previous version and their user impact in subsequent releases. Do not expand the entire commit history into a feature list.
- A useful order is version overview, downloads and prerequisites, main features or changes, upgrade guidance and known limitations, then documentation and feedback links. Adapt it to the release. Put prerequisites such as model keys, search services, account permissions, and potential costs before long feature lists.
- Verify download links against actual asset names, versions, operating systems, and architectures. Use version-specific links in published release notes instead of `latest`, which may point to another version. Separate installation from source-build instructions so ordinary users need not read build procedures first.
- Describe observable user behavior. Move protocol fields, internal retry budgets, process timeouts, and similar details to developer documentation. Do not promote minor styling adjustments without user impact as initial-release highlights. For meaningful fixes, briefly describe the trigger and outcome.
- Retain applicable information about data flows, service dependencies, signing, upgrade migration, and feature limitations. Do not equate local execution with offline operation or citations and review with guaranteed accuracy. Describe key storage, file permissions, and omission of secrets from API responses separately and precisely.
- Keep Chinese and English versions consistent in feature scope, prerequisites, certainty, download links, and limitations. Translate naturally without adding promises. Link to detailed implementation documentation instead of repeating it throughout both language versions.
- Store repository release notes in `docs/releases/<tag>.md`. When synchronizing a GitHub Release, verify its online body; editing a local file does not update the published page. Wording-only changes must not recreate tags or replace online installers. Clearly distinguish local commits, remote pushes, and published-page updates when reporting completion.

### Public Claims and Pre-Commit Review

- Background information supplied to explain authorization, collaboration, or development does not automatically authorize publishing a product-affiliation claim. Unless the user explicitly requests that public wording, describe the project's purpose neutrally. Do not infer claims such as "a team sub-product," "officially produced," "officially authorized," or organizational endorsement; do not infer the opposite labels, such as "unofficial" or "independent derivative," either. If such claims are unnecessary, omit them rather than introducing an extra confirmation step.
- Distinguish project purpose, developer identity, asset provenance, usage licenses, and user access requirements. Attribution does not replace authorization, and a code license does not extend to brand assets or community data. State only confirmed information appropriate for publication.
- Before committing, verify copy against the actual version, implementation, defaults, commands, paths, asset names, and validation evidence. Check bilingual consistency, Markdown formatting, local links, and heading anchors. Remove conversational background, repetition, and unsupported affiliation or performance claims. Follow the Chinese copywriting guidance above when editing Chinese text; do not sacrifice accuracy for a uniform template.

## Security & Configuration

Keep secrets in ignored `.private/` files. User settings are stored in `.private/settings.json`; the application must not read or generate `.env`. Only deployment ports and storage paths use process environment variables. Never expose credentials in frontend responses, logs, or screenshots. Preserve loopback defaults, explicit mock labeling, and sanitized errors. Live failures must not silently return mock results. Do not introduce Rust or `danta-cli` as runtime dependencies.
