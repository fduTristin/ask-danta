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

## UI Design and Local Release

- UI 设计优先参考 ChatGPT 网页端和桌面端的布局、交互与视觉层级，并保留本项目的品牌与中文文案。
- 每次完成新改动后，必须在本地执行 `npm run desktop:dist`，将构建产物输出到 `release/`。如已有文件被运行中的应用占用，可使用 `release/` 下的独立子目录；交付时说明实际路径与验证结果。

## Coding Style & Naming Conventions

Use four-space Python indentation, `snake_case` functions/modules, and `PascalCase` classes. Add type annotations to new interfaces and validate external data with Pydantic.

Use two-space TypeScript indentation, single-quoted strings, semicolons, `PascalCase` components/types, and `camelCase` functions/state. Preserve Chinese UI copy. No formatter or linter is configured; follow surrounding code and avoid unrelated reformatting.

## 中文文档与叙述规范

适用于 README、项目文档、中文 PR 描述、发版说明、界面说明和演示文案。默认使用正式、直接、自然的现代汉语；提交信息仍遵循下方的英文约定。用户明确指定文体时，以用户要求为准。

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

PR 描述面向未参与开发过程的审阅者，解释本次代码差异；Release 面向使用该版本的用户，解释可用功能、安装与升级。两者分别编写，不直接复制提交列表或聊天记录。

- 标题概括最终改动及其作用；正文先写具体问题与改动后的行为。需要时用触发条件、改动前后示例帮助理解，避免“优化体验”“完善功能”等无法核验的概括。
- 按改动复杂度说明范围、必要的实现理由、验证结果及实际限制。简单修改可以只写一两段与验证说明，不强套固定章节；复杂修改再按内容分节。
- 只写帮助审阅的技术细节。删除开发流水账、已放弃方案和与最终差异无关的修复过程；确实影响设计取舍时才解释历史原因。范围变化后同步更新标题和正文。
- 验证说明列出实际执行的检查及结果，区分自动化测试、模拟响应、真实服务联调和人工验证。不将构建通过写成完整功能验收；未验证的重要部分如实说明原因。
- 关联确实相关的 Issue 或计划条目；界面改动附脱敏截图。涉及破坏性变更时说明受影响用户与迁移方法。没有对应 Issue、测试结果或性能数据时不得编造。

### Release Notes

- 发布说明以对应标签与实际分发的安装包为准，不将当前工作区、主分支或计划中的功能写成已发布。首次发布介绍主要能力，后续版本突出相对上一版的变化与用户影响；不把项目建立以来的所有提交展开成清单。
- 建议按“版本简介—下载与使用条件—主要功能或变更—升级说明与已知限制—文档与反馈入口”组织，按版本实际需要取舍。把模型密钥、搜索服务、账号权限及可能产生费用等影响使用的条件放在功能长列表之前。
- 下载链接核对实际资产名称、版本、系统和架构；已发布版本给出对应版本的链接，不使用可能跳转到其他版本的 `latest` 代替。安装与源码构建入口分开，普通用户无需先阅读构建流程。
- 功能描述采用用户能观察到的行为。协议字段、内部重试预算、进程等待时间等细节放入开发文档；没有用户影响的样式微调不作为首次发版亮点。确有用户影响的修复可简述触发条件与修复结果。
- 保留实际适用的数据流向、服务依赖、签名状态、升级迁移和功能限制。避免将“本地运行”写成“离线运行”，或将“引用与核对”写成准确性保证；密钥存储方式、文件权限和接口不返回原文应分别准确说明。
- 中英文版本的功能范围、前提、确定程度、下载链接与限制保持一致。允许自然翻译，不在翻译中新增承诺；长篇实现说明通过文档链接提供，不在双语正文中重复堆叠。
- 仓库发布说明保存在 `docs/releases/<tag>.md`。需要同步 GitHub Release 时核对线上正文；修改本地文件不代表线上已更新。仅修改文案时不重建标签、不替换线上安装包；交付时明确本地提交、远程推送和线上发布页各自的状态。

### 公开表述与提交前核对

- 用户为解释授权、合作或开发背景提供的信息，不自动视为要求公开披露的产品定位。除非用户明确要求对外这样表述，否则使用中性的项目用途描述，不据此新增“团队子产品”“官方出品”“官方授权”或组织背书声明，也不反向推断为“非官方”或“独立衍生”。不需要此类声明即可完成任务时，直接省略，不为文案额外增加确认流程。
- 区分项目用途、开发主体、素材来源、使用许可和用户访问条件。致谢不替代授权说明，代码许可证不扩大为品牌素材或社区数据的许可；只陈述已确认且适合公开的信息。
- 提交前核对文案与实际版本、实现、默认值、命令、路径、资产名称和验证证据；检查中英文一致性、Markdown 格式、本地链接和标题锚点。删除聊天背景、重复信息与未经证实的关系或性能声明。文案修订遵循上方中文规范，不用统一模板牺牲准确性。

## Security & Configuration

Keep secrets in ignored `.private/` files. User settings are stored in `.private/settings.json`; the application must not read or generate `.env`. Only deployment ports and storage paths use process environment variables. Never expose credentials in frontend responses, logs, or screenshots. Preserve loopback defaults, explicit mock labeling, and sanitized errors. Live failures must not silently return mock results. Do not introduce Rust or `danta-cli` as runtime dependencies.
