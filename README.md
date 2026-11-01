# 校内信息研究助手 · Campus Agent

面向本机单用户的校园信息调研应用，采用 React + TypeScript + Vite、FastAPI + HTTPX。
已完成 [开发计划](plan.md) 的**第一步、第二步及其基础回答质量补充**：配置与本地启动、DeepSeek 多轮对话、有预算的搜索/网页读取循环、回答核对与来源展示。固定案例和真实服务结果见 [质量验收记录](docs/quality-evaluation.md)。树洞登录和 Skill 加载尚未实现。

## 快速启动

依赖：Python 3.11+、[uv](https://docs.astral.sh/uv/getting-started/installation/)、Node.js 22.12+（建议 24 LTS）及 npm。
不需要 Rust、`danta-cli`、模型密钥或树洞凭据即可启动离线样例。

在项目根目录执行（PowerShell、macOS / Linux 终端均可；部分系统使用 `python3`）：

```powershell
python scripts/setup.py
python scripts/dev.py
```

安装脚本使用 `uv.lock` 和 `frontend/package-lock.json` 安装依赖，并在 `.env` 不存在时从 `.env.example` 复制；已有配置不会被覆盖。
启动脚本自动使用项目 `.venv`，同时启动两项服务。看到 `Ready` 后访问：

- 工作台：[http://127.0.0.1:5173](http://127.0.0.1:5173)
- 健康检查：[http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)
- API 文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

服务只监听 `127.0.0.1`。前端通过 Vite 将 `/api` 转发给后端，无需跨域配置。按 **Ctrl+C** 关闭两项服务；一项意外退出时，启动脚本也会停止另一项。端口占用会明确报错，不会自动切换端口。

前端支持热更新；修改后端代码或根目录 `.env` 后需重启启动脚本。

## 本地配置

编辑根目录 `.env`。真实密钥只放在本地文件或环境变量里，不写入源码、截图或聊天。环境变量优先于 `.env`。
后端按仓库绝对位置加载配置，相对凭据路径始终相对于仓库根目录。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MODEL_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容模型接口基址 |
| `MODEL_NAME` | `deepseek-flash` | DeepSeek 对话与工具调用使用的模型名 |
| `MODEL_API_KEY` | 空 | DeepSeek API Key |
| `MODEL_THINKING` | `disabled` | `enabled` / `disabled`，不向前端展示思考内容 |
| `MODEL_REASONING_EFFORT` | `low` | 开启思考时使用：`low` / `high` / `max` |
| `MODEL_MAX_TOKENS` | `4096` | 模型输出上限，256–32768 |
| `MODEL_TIMEOUT_SECONDS` | `45` | 单次模型请求的 HTTP 超时及整体截止时间 |
| `ANSWER_REVIEW_ENABLED` | `true` | 对使用资料/引用的候选回答进行核对；若核对触发补查，最终稿再核对一次（最多两次） |
| `SEARCH_PROVIDER` | `mock` | `mock` 为离线样例；`tavily` 为真实搜索 |
| `SEARCH_API_KEY` | 空 | Tavily API Key |
| `SEARCH_MAX_RESULTS` | `5` | 单次最多 1–10 条结果 |
| `SEARCH_MAX_SNIPPET_CHARS` | `2000` | 每条摘要最多 100–10000 个字符，截断有标记 |
| `SEARCH_DEPTH` | `advanced` | Tavily `basic` / `advanced`；深入搜索可能消耗更多额度 |
| `SEARCH_TIMEOUT_SECONDS` | 未单独设置 | 搜索及网页读取超时；未设置时沿用 `HTTP_TIMEOUT_SECONDS` |
| `CAMPUS_AUTH_FILE` | `.private/campus-tokens.json` | 为第三步预留；当前只检测文件是否存在，不读取内容 |
| `HTTP_TIMEOUT_SECONDS` | `15` | 兼容原配置，作为搜索/网页读取的默认超时；模型使用独立配置 |
| `MAX_TOOL_CALLS` | `6` | 每轮用户请求最多尝试的工具调用数；无效参数和未知工具也计数 |
| `MAX_CAMPUS_PAGES` | `3` | 第三步校内检索分页预算，当前仅配置 |
| `REQUEST_BUDGET_SECONDS` | `90` | 单轮 Agent 总时长，包含检索与最终回答 |
| `BACKEND_PORT` | `8000` | 后端端口，1024–65535 |
| `FRONTEND_PORT` | `5173` | 前端端口，1024–65535，须与后端不同 |

模型默认值依据 [DeepSeek 官方 API 文档](https://api-docs.deepseek.com/)（2026-11-01 核对）。健康检查中的密钥状态只代表“已配置”，不会调用外部服务验证密钥。

启用对话：填写 `MODEL_API_KEY` 并重启服务。适配器通过 HTTPX 请求 `MODEL_BASE_URL/chat/completions`，使用 [DeepSeek 官方工具调用协议](https://api-docs.deepseek.com/guides/tool_calls/)。默认关闭思考；开启后按[思考模式协议](https://api-docs.deepseek.com/guides/thinking_mode/)在服务内存中保留并回传工具轮次的 `reasoning_content`，不返回前端、不写入评测报告。一次用户提问可能触发多次模型与搜索请求并消耗相应额度；用户问题、会话历史、检索摘要及读取的网页文本会发送给模型，检索词发送给 Tavily。固定案例中单独开启思考仍会出现无依据的距离，因此当前默认采用非思考模式、深入检索和有次数上限的发布前核对；这不是模型正确性的保证。

启用真实网页搜索：

```dotenv
SEARCH_PROVIDER=tavily
SEARCH_API_KEY=在本地填入你的密钥
```

重启服务后，工作台显示 Tavily 模式。搜索请求会将输入的关键词发送至 Tavily；该请求可能消耗服务额度。
API 使用 [Tavily 官方 Search 接口](https://docs.tavily.com/documentation/api-reference/endpoint/search)，固定请求 `https://api.tavily.com/search`，以 Bearer token 认证。不请求服务生成的回答或网页全文。

- `mock` 模式不访问网络，所有查询返回相同的**合成样例**。样例地址使用保留域名 `example.invalid`，页面不将其渲染为来源链接。
- `tavily` 缺少密钥时服务仍可启动，但搜索返回 `503 search_not_configured`。
- 认证失败、限流/额度不足、超时、网络错误、响应格式变化均返回明确错误，**不会自动降级为样例**。
- 返回来源链接、标题、摘要、可用日期、截断标记；按 URL 去重。上游未提供日期时为 `null`，不会编造日期。空结果是成功返回的空列表。
- 健康检查不请求外部服务，不返回密钥、凭据路径或 token 内容。此阶段未验证树洞凭据有效性。

## API 契约

`GET /api/health` 返回 `stage=2`、运行状态、非敏感配置状态和预算。`status=ok` 只代表本地后端存活；`model.chat_enabled` 表示已配置可发起对话。`model.available` 保持 `false`（健康检查不验证远端可用性），`campus.available` 为 `false`（尚未接入）。

`POST /api/search` 保留为独立搜索验证入口；同一搜索适配器已注册为 Agent 的 `search_web(query)` 工具。请求：

```json
{ "query": "复旦大学 校园办事指南" }
```

统一成功响应（此处是结构示例）：

```json
{
  "query": "复旦大学 校园办事指南",
  "provider": "mock",
  "is_mock": true,
  "notice": "离线固定样例：未访问网络，内容与查询无关，不可作为办事依据。",
  "results": [
    {
      "source": "web",
      "title": "校园办事指南（合成样例）",
      "url": "https://example.invalid/campus-guide",
      "snippet": "合成的展示文字，不包含实际办事要求。",
      "published_at": null,
      "truncated": false
    }
  ]
}
```

输入关键词会去除首尾空白，长度必须为 1–500 个字符，非法请求返回 `422`。搜索服务错误格式：

```json
{ "error": { "code": "search_timeout", "message": "搜索超时，请稍后重试。" } }
```

## 对话、会话与事件流

页面提供新建会话、清空会话、多轮追问、调用进度、来源卡片和停止回答。来源编号如 `[W1]` 在同一会话中保持稳定，并按 URL 去重；日期仅来自搜索返回值。前端安全地以纯文本显示回答和摘要，来源卡片链接只采用搜索适配器校验后的 HTTP(S) URL。每条回答的“本回答引用”只列该回答实际引用的来源；另有“会话累计检索”供查看全部结果。两者均标明搜索摘要/已读取网页文本及截断情况；出现引用不等于语义上一定得到来源支持。

| 接口 | 用途 |
| --- | --- |
| `POST /api/sessions` | 新建会话，返回 `session_id`、空历史与来源 |
| `GET /api/sessions/{session_id}` | 读取已完成的用户/助手消息、来源与忙碌状态 |
| `POST /api/sessions/{session_id}/clear` | 清空历史、用户条件与检索来源，保留会话 ID |
| `DELETE /api/sessions/{session_id}` | 删除会话 |
| `POST /api/sessions/{session_id}/chat` | 请求体 `{"message":"你的问题"}`，返回 SSE 事件流 |

问题去除首尾空白，限 1–8000 字符。无效输入返回 `422`；不存在的会话返回 `404`；同一会话正在回答时，重复发送、清空或删除返回 `409`；未配置模型返回 `503 model_not_configured`。流建立前的错误为 JSON，流中的上游失败通过 `error`/`tool_error` 事件报告。

前端使用 `fetch` 读取 POST 响应体，每帧格式为 `data: {JSON}\n\n`。事件包括：

- `start`、`model_start`：本轮开始与模型工作状态。
- `tool_start`：调用 ID 和工具名；`tool_complete`：同一 ID 和工具结果，搜索返回 `query/results`，读取返回 `source_id/url/title/text/truncated`；`tool_error`：同一 ID 和脱敏错误。
- `review_start`：正在核对候选答案，候选文本不展示、不写入历史；核对可在原预算内触发补查。
- `budget`：停止进一步检索的原因；`error`：模型或总预算失败。
- `final`：`message` 含最终文本、仅引用的 `sources`、警告、`limited`、`reviewed` 与 `status`；另附全部 `session_sources`、实际尝试的 `tool_calls`，以及 `metrics` 中的模型调用次数、上游可取得的 token 用量和耗时。`status=incomplete` 表示预算或故障等导致未完成；`complete` 仅表示完成回答流程，不是事实正确性的评分。

工具按白名单执行，参数经 Pydantic 校验，结果按模型返回的 `tool_call_id` 回填。并列调用也按顺序执行，超过预算的调用回填明确错误。同一轮重复的工具名和参数（忽略大小写及多余空白）不会再次请求上游，但占用一次尝试；相似含义的不同关键词仍由模型判断。网页内容是不可信资料，不能授予工具权限；目前没有任意 URL 读取或社区写操作工具。

默认模型请求 45 秒、搜索/读取 15 秒，每轮最多 6 次工具尝试、总计 90 秒。为最终回答预留 `min(MODEL_TIMEOUT_SECONDS, REQUEST_BUDGET_SECONDS / 3)` 秒（默认 30 秒）；检索阶段达到截止时间或工具上限后，移除工具并要求模型基于已有资料说明缺口。最终模型调用和核对均受总时长约束；模型失败或总时长耗尽时，应用返回**明确标注未完成核对的已取回摘要**，不会伪装成完整研究结论。`MAX_CAMPUS_PAGES=3` 供第三步使用，当前没有校内检索工具。

当前工作流：普通聊天或条件确认直接回答；需要查证时检索，结果无关或证据不足时改词补查；摘要缺少关键事实可读取已命中页面；有检索资料或引用的候选答案进行额外模型核对，必要时继续补查。如果核对触发了补查，最终稿再核对一次，此时禁止继续开启工具，最多两次核对均计入原总时长。不存在的来源编号和 mock 引用会被程序拒绝；引用是否真正支持结论仍依赖模型核对与质量评测，不是自动证明。

`read_web(source_id)` 只接受本会话已检索到的来源编号，如 `W1`。每次 DNS 解析和每一次重定向都要求地址为公开 HTTP(S)、标准端口且不含认证信息；拒绝本机、内网、保留地址、混合公私地址与 IPv4 映射地址。连接固定到通过校验的 IP，保持原 Host/TLS SNI，禁用环境代理，最多 3 次跳转。读取不携带模型/搜索密钥或浏览器凭据，只接受 HTML/纯文本，最多 1 MB 内容、12000 字符并标注截断。暂不支持 PDF、登录页面或依赖 JavaScript 的页面；HTML 提取可能仍带部分导航，不能宣称完整阅读所有正文。

会话只保存在单进程内存中，重启后丢失，不支持多 worker 或多用户部署。页面将当前会话 ID 放入 `sessionStorage`，刷新可恢复已完成消息；新建会话使用独立 ID，不读取旧历史。新建不会删除旧会话，删除接口或服务重启可释放旧会话。停止或断开连接会取消正在进行的上游请求并释放会话占用；尚未完成的整轮不写入历史。已发送的上游请求仍可能产生费用。当前未做长对话压缩或持久化。

## 验证

```powershell
uv run --frozen pytest -q
npm --prefix frontend run build
python scripts/dev.py --smoke
```

`--smoke` 会临时启动前后端，检查健康接口、页面和代理，随后关闭两项服务；先停止已有开发服务，避免端口冲突。
测试不读取本地 `.env`，使用 HTTPX 模拟外部响应，不产生模型或搜索费用。

真实搜索验收：先填写 Tavily 配置并启动服务，再在另一个终端执行：

```powershell
python scripts/check_search.py
python scripts/check_chat.py
# 自定义端口时：python scripts/check_search.py --port 8001
```

脚本拒绝把 mock 结果记为真实验收通过，只输出提供商、数量及来源 URL。也应在页面手动搜索并打开来源，核对标题、摘要和相关性。
`check_chat.py` 会新建独立测试会话，要求模型实际搜索、验证最终回答包含来源编号，再追问校区条件，最后删除该测试会话；上游失败、无工具结果或 mock 来源都不算通过。两项脚本均支持 `--port`。

质量评测与接口冒烟分开运行。以下命令会读取本地配置、调用真实 DeepSeek，并在 3 个 live 案例调用 Tavily/公开网页，产生服务费用；其余案例为明确标注的合成检索/正文搭配真实模型，不属于真实检索验收：

```powershell
uv run --frozen python scripts/evaluate_quality.py --label local-check
uv run --frozen python scripts/evaluate_quality.py --label thinking-check --thinking enabled --case distance
```

报告保存到忽略目录 `.private/quality/`，包含固定问题、回答、证据、调用记录与用量，不保存密钥或思考内容。脚本采集结果，需人工逐项核对；不会用“接口成功”或引用数量自动判定通过。已有前后对比、未成功的中间结果和默认值选择见 [质量验收记录](docs/quality-evaluation.md)。

2026-11-01 验证记录：

- **自动化模拟验证**：60 项测试通过。覆盖搜索/配置、工具协议、追问历史、会话隔离、清空/删除、参数校验、预算、上游错误与取消清理；补充候选答案修正、补查与去重、未知引用阻断、思考协议及用量、独立超时、网页读取地址限制/DNS 固定/重定向/截断/错误脱敏，以及核对阶段取消后不提交历史。测试不读取本地凭据、不访问外网；有一条依赖库 TestClient 的弃用提示，不影响结果。
- **构建与启动验证**：TypeScript 检查与生产构建通过；无 `.env`、无树洞凭据启动前后端与代理检查通过。开发启动不导入或执行 Rust / `danta-cli`，不依赖参考仓库。
- **浏览器验证**：第一步工作台检查保留；第二步桌面与窄屏对话、工具进度、真实来源展开、追问条件、刷新恢复会话、停止回答、清空历史与来源通过。验收截图在本地忽略目录 `.private/verification/`。
- **Tavily 真实服务验证（通过）**：用户完成本地配置后，`python scripts/check_search.py` 查询“复旦大学 官方网站”，返回 5 条真实结果。随后在浏览器查询 `site.fudan.edu.cn 在读证明 办理`，再次返回 5 条结果，页面显示实际来源链接、服务提供的日期及“日期未知”。已打开并核对其中的[复旦大学研究生院](https://gs.fudan.edu.cn/)来源，标题与页面内容一致。两次请求均使用实际 Tavily API，未使用模拟响应，未调用模型。
- **检索质量观察**：真实返回同时包含较旧资料、校外转载和其他学校页面。关键词中的 `site:` 不应视为应用强制执行的域名过滤；后续 Agent 必须核对实际域名、相关性与时效性，不能直接将所有命中视为有效办事依据。本次只验收搜索接入及展示，不认定办事要求已核实。
- **DeepSeek + Tavily 真实服务验证（通过）**：2026-11-01 执行 `python scripts/check_chat.py`，`deepseek-flash` 实际调用 `search_web`，Tavily 返回 5 条真实来源（包含 `https://gs.fudan.edu.cn/`），模型按来源编号回答；后续不搜索的追问保留了“江湾”条件。浏览器另做一次真实检索和追问，通过事件流显示结果。浏览器中也在搜索进行时停止请求，未完成轮次未留入历史，随后清空成功。此记录验收调用链，不代表摘要内的所有事实都已人工核实。
- **第二步补充验证**：固定 10 组案例的基线、失败中间结果和最终逐项记录见质量报告；最终记录包括修复后的定向复测，不代表单次全量通过。真实官网查询、正文读取及条件追问通过；距离题最后一次未查明里程，只通过证据边界检查。浏览器验证核对进度、回答引用与累计来源分组、已读正文标记，390px 窄屏无横向溢出，控制台无错误。
- **尚未执行的真实服务验证**：树洞接口联调留在第三步。

## 目录

```text
frontend/                 React + TypeScript 工作台
backend/app/              FastAPI、会话、Agent 循环、模型与网页搜索适配器
skills/campus-research/   Skill 预留目录，第四步实现与加载
tests/                    隔离真实凭据的模拟测试
scripts/                  安装、启动与真实搜索/对话验收脚本
.env.example              不含真实密钥的配置示例
pyproject.toml / uv.lock   Python 依赖与锁文件
```

后续范围见 [plan.md](plan.md)。树洞独立登录在第三步，Skill 加载、数据源权限与进一步完善产品交互在第四步；第二步已提供可验收的基础对话界面。
`npm run build` 当前验证静态前端可构建；`vite preview` 不提供后端代理，日常运行请使用上述开发启动入口。

本地 `.env`、`.private/`、依赖、日志与构建目录均由 `.gitignore` 排除。后续提交压缩包时同样需要排除这些目录及 `.git`。
