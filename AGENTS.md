# Repository Guidelines

## Project Structure & Module Organization

- `backend/app/`: FastAPI application factory (`main.py`), environment settings (`config.py`), and HTTPX search adapter (`search.py`).
- `frontend/src/`: React/TypeScript interface and CSS; keep UI assets here. `frontend/vite.config.ts` configures the `/api` development proxy.
- `tests/`: backend and adapter tests using synthetic responses.
- `scripts/`: dependency installation, development server supervision, and live-search checks.
- `skills/campus-research/`: reserved for the research Skill; loading is not implemented yet.
- `plan.md`: milestones. Update it and `README.md` when behavior changes; distinguish implemented features from plans.

## Build, Test, and Development Commands

Use Python 3.11+, uv, and Node.js 22.12+ with npm. Run from the repository root:

- `python scripts/setup.py`: install locked dependencies and create `.env` if absent.
- `python scripts/dev.py`: start frontend and backend on loopback; Ctrl+C stops both.
- `uv run --frozen pytest -q`: run isolated backend tests.
- `npm --prefix frontend run build`: check TypeScript and build frontend assets.
- `python scripts/dev.py --smoke`: start, verify, and stop both servers; stop existing development servers first.
- `python scripts/check_search.py`: validate actual Tavily search against a running backend; requires live configuration and consumes service quota.

## Coding Style & Naming Conventions

Use four-space Python indentation, `snake_case` functions/modules, and `PascalCase` classes. Add type annotations to new interfaces and validate external data with Pydantic.

Use two-space TypeScript indentation, single-quoted strings, semicolons, `PascalCase` components/types, and `camelCase` functions/state. Preserve Chinese UI copy. No formatter or linter is configured; follow surrounding code and avoid unrelated reformatting.

## Testing Guidelines

Use pytest, FastAPI `TestClient`, and HTTPX `MockTransport`. Name files `test_*.py` and functions `test_*`. Tests must ignore local credentials and avoid external requests. Cover changed behavior, validation, upstream failures, and secret redaction. No numerical coverage threshold is configured. Record live verification separately from mocked tests; check desktop and narrow layouts for UI changes.

## Commit & Pull Request Guidelines

### Commit Convention

Write commit messages in English using this format:

```text
<type>(<scope>): <summary>
```

- Use types such as `feat`, `fix`, `docs`, `refactor`, `test`, `build`, `ci`, or `chore`.
- Scope is optional; use stable module names such as `auth`, `posts`, or `search`. Keep the summary short, specific, and imperative, without a trailing period.
- When details are needed, leave a blank line after the subject and write the body as unordered list items beginning with `- `. Omit the body for simple commits.
- Keep commits atomic. Do not mix unrelated formatting, dependency, or version changes, or merge temporary commits such as `WIP` or `fixup!`.
- For breaking changes, use `<type>(<scope>)!: <summary>` (or `<type>!: <summary>` without a scope) and include a `BREAKING CHANGE:` footer explaining the impact and migration steps.

### Pull Requests

PRs should explain behavior, scope, validation, and limitations. Link issues or plan milestones; include screenshots for UI changes.

## Security & Configuration

Keep secrets in ignored `.env` or `.private/` files; only commit placeholders in `.env.example`. Never expose credentials in frontend responses, logs, or screenshots. Preserve loopback defaults, explicit mock labeling, and sanitized errors. Live failures must not silently return mock results. Do not introduce Rust or `danta-cli` as runtime dependencies.
