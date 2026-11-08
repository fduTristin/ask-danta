# Repository Guidelines

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

## Coding Style & Naming Conventions

Use four-space Python indentation, `snake_case` functions/modules, and `PascalCase` classes. Add type annotations to new interfaces and validate external data with Pydantic.

Use two-space TypeScript indentation, single-quoted strings, semicolons, `PascalCase` components/types, and `camelCase` functions/state. Preserve Chinese UI copy. No formatter or linter is configured; follow surrounding code and avoid unrelated reformatting.

## 中文文档与叙述规范

适用于 README、项目文档、中文 PR 描述、界面说明和演示文案。默认使用正式、直接、自然的现代汉语；提交信息仍遵循下方的英文约定。用户明确指定文体时，以用户要求为准。

### 内容与语气

- 先说明项目用途、实际行为或操作结果，再补充必要的条件与限制。使用具体名词和动词，避免形容词堆砌、官样表达和聊天式开场。
- 每句话应提供信息。删除没有实际含义的口号、夸赞、铺垫和重复总结，不用“赋能”“极致体验”“一站式解决”等词代替功能说明。不添加“值得注意的是”“综上所述”等无必要的过渡语。
- 直接陈述事实，不为抬高语气编造“不是 X，而是 Y”“不仅……更……”式对比。真实的差异、否定和限制必须保留；这些句式不是机械禁用词。
- 保留原文的条件、范围、归因和确定程度。区分已实现、计划中、模拟演示和实际验证，不把“支持来源引用”写成“保证回答准确”。不得为了让文案具体而虚构数据、用户评价、性能结论或个人经历。
- 正式不等于冗长，自然不等于口语化。不强加感叹、反问、俏皮话或人格化描述，也不为追求短句破坏句意与段落衔接。

### 文档组织与排版

- README 面向首次接触项目的读者，说明用途、主要功能、部署配置、使用边界及必要的开发入口。不要写成宣传稿、对话回复或开发流水账；阶段进展和验证记录放在 `plan.md`，详细专题另设文档并链接。
- 标题直接标明内容，例如“部署与配置”“数据管理与使用边界”。正文以连贯段落为主；并列信息使用列表，操作步骤使用编号，参数或方案对比使用表格。不为形式整齐强凑三点、拆分小标题或添加重复总结。
- 中文正文使用中文标点，中文与英文、阿拉伯数字之间留一个半角空格，英文或数字与中文标点之间不留空格。保留专有名词的官方拼写，术语在全文中保持一致。
- 命令、标识符、路径、URL 和配置值保持原样，不因文字润色改变大小写、引号或空格。修改标题后检查相关锚点；链接文字说明目标内容，避免“点击这里”。

### 演示与宣传素材

- 默认以实际界面和操作过程展示产品。片头片尾可保留项目名称与标识；未经用户明确要求，不添加宣传口号、旁白、解释性字幕或号召使用的结尾。
- 保留界面自身必要的状态和数据标识。演示数据的性质及使用限制在 README 的演示说明中交代，不额外叠加重复的宣传文字。
- 文案需要补充时，只描述画面中可观察到的功能，不替用户评价体验，不加入“每一步，都看得见”等抽象表述。

以下示例仅在对应功能确已实现时使用：

| 避免的表达 | 建议表达 |
| --- | --- |
| 校园里的问题，有据可查。 | 支持公开网页与树洞检索，并提供来源引用。 |
| 每一步，都看得见。 | 界面显示工具调用状态与耗时。 |
| 轻松开启你的智能校园探索之旅。 | 运行 `python scripts/dev.py` 启动服务。 |

提交前核对事实、命令、默认值、路径和链接，删除重复信息，确认没有因润色扩大功能承诺。纯文档措辞修改不要求运行应用测试；涉及操作说明时，应核对相应实现或验证命令。

参考资料：[Humanizer-zh](https://github.com/op7418/Humanizer-zh/blob/main/SKILL.md)（中文润色 skill）与[中文技术文档的写作规范](https://github.com/ruanyf/document-style-guide)（写作指南）。仅参考适合本项目的表达与排版建议，不自动安装外部 skill，不照搬固定句长或改写模板；本节以项目实际需求和用户要求为准。

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
- Commit promptly after each small, coherent change is complete and its relevant checks pass. Do not wait until the entire task or milestone is finished, or for a separate user reminder; keep each commit independently reviewable.
- For breaking changes, use `<type>(<scope>)!: <summary>` (or `<type>!: <summary>` without a scope) and include a `BREAKING CHANGE:` footer explaining the impact and migration steps.

### Pull Requests

PRs should explain behavior, scope, validation, and limitations. Link issues or plan milestones; include screenshots for UI changes.

## Security & Configuration

Keep secrets in ignored `.private/` files. User settings are stored in `.private/settings.json`; the application must not read or generate `.env`. Only deployment ports and storage paths use process environment variables. Never expose credentials in frontend responses, logs, or screenshots. Preserve loopback defaults, explicit mock labeling, and sanitized errors. Live failures must not silently return mock results. Do not introduce Rust or `danta-cli` as runtime dependencies.
