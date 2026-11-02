# 校内信息研究助手 · Campus Agent

面向本机单用户的校园信息调研应用，采用 React + TypeScript + Vite、FastAPI + HTTPX。
已实现 [开发计划](plan.md) 的**第一至第四步**，并执行**第五步测试与演示及追加修复**：DeepSeek 多轮对话、网页搜索与正文读取、树洞登录与只读工具、跨来源引用、数据源权限和校园调研 Skill。152 项隔离测试通过，固定质量案例扩至 18 组。本轮修复认证失效恢复、证据适用范围、引用与字数约束，并验证真实调用链；距离题按用户要求不做专项优化。质量验收仍有漏补查、楼层编号表述及短帖逐字引用等残留，真实 token 过期刷新尚未主动触发。最新结果见 [第五步追加修复记录](docs/stage5-repair-verification.md) 与 [脱敏修复样本](docs/stage5-repair-samples.json)；此前失败和演示保留在 [原第五步验收记录](docs/stage5-verification.md)。

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
| `ANSWER_REVIEW_ENABLED` | `true` | 使用独立证据核对断言，再按具体问题修订；每轮最多 4 次核对/改写，共享原总时长。关闭只跳过常规语义核对，引用和显式字数校验仍保留 |
| `SEARCH_PROVIDER` | `mock` | `mock` 为离线样例；`tavily` 为真实搜索 |
| `SEARCH_API_KEY` | 空 | Tavily API Key |
| `SEARCH_MAX_RESULTS` | `5` | 单次最多 1–10 条结果 |
| `SEARCH_MAX_SNIPPET_CHARS` | `2000` | 每条摘要最多 100–10000 个字符，截断有标记 |
| `SEARCH_DEPTH` | `advanced` | Tavily `basic` / `advanced`；深入搜索可能消耗更多额度 |
| `SEARCH_TIMEOUT_SECONDS` | 未单独设置 | 搜索及网页读取超时；未设置时沿用 `HTTP_TIMEOUT_SECONDS` |
| `CAMPUS_AUTH_FILE` | `.private/campus-tokens.json` | 本项目独立登录保存的 token 对；健康检查读取并校验本地结构，不请求远端，也不返回凭据内容 |
| `CAMPUS_MAX_CONTENT_CHARS` | `4000` | 每条树洞正文最多 100–12000 字符，截断有标记 |
| `HTTP_TIMEOUT_SECONDS` | `15` | 树洞 HTTP 超时及搜索/网页读取的默认超时；模型使用独立配置 |
| `MAX_TOOL_CALLS` | `6` | 每轮用户请求最多尝试的工具调用数；无效参数和未知工具也计数 |
| `MAX_CAMPUS_PAGES` | `3` | 同一树洞工作流共享的分页尝试预算；独立 HTTP 入口一次读取一页 |
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
- 健康检查不请求外部服务，不返回密钥、凭据路径或 token 内容；本地凭据状态不能代替远端认证。

## API 契约

`GET /api/health` 返回 `stage=5`、运行状态、非敏感配置状态和预算。`status=ok` 只代表本地后端存活；`model.chat_enabled` 表示已配置可发起对话。`model.available` 与 `campus.available` 保持 `false`（健康检查不验证远端可用性）；`campus.credentials_present` 仅表示文件存在；`auth_state` 为 `missing/invalid/expired/configured`，`tools_enabled` 代表本地凭据可用于尝试调用，不保证远端仍有效。`skills` 列出已加载的 `campus-research`。

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
| `POST /api/sessions/{session_id}/chat` | 请求体 `{"message":"你的问题","source_mode":"all"}`，返回 SSE 事件流 |

问题去除首尾空白，限 1–8000 字符。无效输入返回 `422`；不存在的会话返回 `404`；同一会话正在回答时，重复发送、清空或删除返回 `409`；未配置模型返回 `503 model_not_configured`。流建立前的错误为 JSON，流中的上游失败通过 `error`/`tool_error` 事件报告。

前端使用 `fetch` 读取 POST 响应体，每帧格式为 `data: {JSON}\n\n`。事件包括：

- `start`、`model_start`：本轮开始与模型工作状态。
- `tool_start`：调用 ID 和工具名；`tool_complete`：同一 ID 和工具结果，搜索返回 `query/results`，读取返回 `source_id/url/title/text/truncated`；`tool_error`：同一 ID 和脱敏错误。
- `review_start`：正在核对候选答案，候选文本不展示、不写入历史；核对可在原预算内触发补查。
- `budget`：停止进一步检索的原因；`error`：模型或总预算失败。
- `final`：`message` 含最终文本、仅引用的 `sources`、警告、`limited`、`reviewed` 与 `status`；另附全部 `session_sources`、实际尝试的 `tool_calls`，以及 `metrics` 中的模型调用次数、上游可取得的 token 用量和耗时。`status=incomplete` 表示预算或故障等导致未完成；`complete` 仅表示完成回答流程，不是事实正确性的评分。

工具按白名单执行，参数经 Pydantic 校验，结果按模型返回的 `tool_call_id` 回填。并列调用也按顺序执行，超过预算的调用回填明确错误。同一轮重复的工具名和参数（忽略大小写及多余空白）不会再次请求上游，但占用一次尝试；相似含义的不同关键词仍由模型判断。网页内容是不可信资料，不能授予工具权限；目前没有任意 URL 读取或社区写操作工具。

默认模型请求 45 秒、搜索/读取 15 秒，每轮最多 6 次工具尝试、总计 90 秒。为最终回答预留 `min(MODEL_TIMEOUT_SECONDS, REQUEST_BUDGET_SECONDS / 3)` 秒（默认 30 秒）；检索阶段达到截止时间或工具上限后，移除工具并要求模型基于已有资料说明缺口。最终模型调用和核对均受总时长约束；模型失败或总时长耗尽时，应用返回**明确标注未完成核对的已取回摘要**，不会伪装成完整研究结论。`MAX_CAMPUS_PAGES=3` 在单轮 Agent 中由搜索和详情工具共享，失败尝试也计页。页数耗尽后移除树洞工具，但剩余网页调用仍可执行；所有工具（包括调研计划）均计入 6 次尝试和 90 秒总时长。

当前工作流：普通聊天或条件确认不检索；需要查证时检索，摘要不足可读取已命中页面。后端从明确的中文搜索/读取指令建立操作清单（不按学校、题目或答案路由），独立核对返回具体修正项，后端对照实际工具尝试检查缺失操作；不能仅改写文字就标为完成。复核可在剩余检索预算内调用工具，并收到已尝试的查询参数以避免重复。明确要求“不再搜索／只用已有资料”时，工具注册和执行均禁止新检索。

核对／格式重试／改写每轮最多4次；核对发起的工具调用计入检索路由，仍占6次工具和原90秒总时长。模型总调用另设上限 `MAX_TOOL_CALLS + 5`（默认11次），不能无限往返。费用核对使用 `facts` 记录服务、渠道、对象与来源原文，程序检查摘录可在对应证据中找到；改写收到这些限定。摘录匹配并不等于自动证明语义正确。

来源编号、显式数字字数上限（如“最多100字”“120字以内”）以及帖子全文复制由程序检查。字数包括标点、空白、格式和引用；帖子按Unicode归一化并忽略标点空白后匹配，至少8个字母或数字才触发，避免“谢谢”等短词误报。复制完整帖子时要求概括，仍失败则明确未完成；兜底不输出树洞正文。语义复核关闭后这些检查仍执行。

模型只看到C引用编号及洞号，不接收数据库楼层ID或基于ID构造的标题；原始ID保留于来源卡和后端映射。重复工具结果的正文只发送最新一份，网页正文已读时复核不重复发送摘要；改写阶段只携带草稿、修正项和费用记录涉及的证据。权限隔离继续执行。`review_calls`、`answer_repairs`、`review_tool_rounds`、`facts_checked` 等指标记录额外工作。

`read_web(source_id)` 只接受本会话已检索到的来源编号，如 `W1`。每次 DNS 解析和每一次重定向都要求地址为公开 HTTP(S)、标准端口且不含认证信息；拒绝本机、内网、保留地址、混合公私地址与 IPv4 映射地址。连接固定到通过校验的 IP，保持原 Host/TLS SNI，禁用环境代理，最多 3 次跳转。读取不携带模型/搜索密钥或浏览器凭据，只接受 HTML/纯文本，最多 1 MB 内容、12000 字符并标注截断。暂不支持 PDF、登录页面或依赖 JavaScript 的页面；HTML 提取可能仍带部分导航，不能宣称完整阅读所有正文。

会话只保存在单进程内存中，重启后丢失，不支持多 worker 或多用户部署。页面将当前会话 ID 放入 `sessionStorage`，刷新可恢复已完成消息；新建会话使用独立 ID，不读取旧历史。新建不会删除旧会话，删除接口或服务重启可释放旧会话。停止或断开连接会取消正在进行的上游请求并释放会话占用；尚未完成的整轮不写入历史。已发送的上游请求仍可能产生费用。当前未做长对话压缩或持久化。

## 对话中的树洞工具与调研 Skill（第四步）

登录后，“本轮允许的数据源”默认采用“自动（公开网页 + 树洞）”。自动选项随本地认证状态变化；手动选择的“仅公开网页”或“公开网页 + 树洞”会在当前浏览器标签页中记住，刷新不会改掉明确选择。允许树洞表示检索正文会被发送给配置的模型服务，不包含登录密码或 token。

对话请求的 `source_mode` 接受 `web` / `all`，省略时由后端根据本地凭据状态决定；非法值返回 422。权限同时控制模型可见工具和实际执行，模型或帖子不能自行开启禁用的数据源。`web` 模式既不调用树洞，也不把既有树洞正文或受其影响的助手回答重新发给模型；保留用户发言中的条件供追问使用。旧来源仍可在页面历史中查看，点击“清空会话”会同时清除全部来源、两套模型历史和聊天消息。

| 工具 | 用途 |
| --- | --- |
| `search_web(query)` / `read_web(source_id)` | 搜索公开网页，按已获得的编号读取正文 |
| `search_campus_posts(query, offset=0, limit=20)` | 搜索树洞楼层；按洞号/楼层 ID 去重并分配 C 编号 |
| `read_campus_thread(hole_id, offset=0, limit=20)` | 读取帖子元数据及一页楼层，核对讨论上下文 |
| `plan_research(questions, gaps, next_action, sources)` | 复杂调研记录或更新子问题、缺口、下一步行动与选用来源 |

网页编号为 `[W1]`，树洞编号为 `[C1]`，分别在同一会话中稳定去重。树洞来源卡片展示洞号、楼层 ID、日期、正文、基础脱敏与截断标记，不生成未经验证的网页链接。读取详情后标为“已读取帖子上下文（部分楼层）”，不声称读完整个帖子。正文在模型工具结果中只保留一份，避免重复发送。

后端启动时从固定路径加载 `skills/campus-research/SKILL.md`。系统提示包含适用条件与指令，模型按需求选用；复杂调研可用 `plan_research` 明确工作计划并更新缺口，普通聊天无需调用工具或输出报告。`start` 事件记录 `skill_loaded` 与 `allowed_sources`；工具事件显示搜索、读取、计划和剩余页数；最终消息记录 `skill`（本轮使用检索/计划时）、`plan` 和 `end_reason=answered/budget/error`。`answered` 只表示流程产生了答案，不代表事实全部核实，具体缺口仍需阅读正文。模型是否合理选择与结束研究须经质量评审，工具注册不能保证每次都正确选择。

发现凭据缺失/失效时会显示限制，移除树洞调用能力，仍可继续使用网页；已成功取回的本轮资料可以说明局限后引用。限流、超时、无权限等错误单独显示，不包装成“没有结果”。所有网页、帖子和引用都作为不可信资料处理，没有发帖、任意 URL 或凭据读取工具。基本防护和权限测试不等于彻底解决所有提示注入风险。

真实跨来源检查（会调用模型、Tavily 和树洞，产生服务费用）：

```powershell
uv run --frozen python scripts/check_research_chat.py
```

该脚本建立独立会话，要求计划→网页搜索→树洞搜索→帖子读取，再切到仅网页进行校区追问，最后删除测试会话。只输出工具名、引用编号、数量和模型用量，不输出完整帖子。脚本验收调用链，不能替代引用与结论的人工核对。

## 树洞网页登录、独立脚本与只读接口（第三步）

**网页登录**：启动应用后，在“服务状态”下点击“登录树洞”，输入邮箱和密码，再点击“登录并保存凭据”。已有凭据时按钮显示“重新登录树洞”。浏览器只向本机的 `POST /api/campus/login` 提交账号密码，由后端调用固定的树洞认证服务；token 仅保存在后端配置的本地文件，响应不包含邮箱、密码或 token。密码框在提交时立即清空，成功后收起表单并刷新凭据状态；应用不把密码写入浏览器存储或会话历史，也不发送给模型。登录失败不覆盖原有凭据，错误提示不会回显输入，即使 JSON 格式错误也会脱敏。

网页登录完成认证和本地凭据保存后，对话的自动数据源选项会变为“公开网页 + 树洞”。也可手动选择仅网页。真实账号登录成功后，可以运行下方检查脚本验证搜索与详情。

如果更新前端后登录始终失败，先确认后端也已重启。Vite 会热更新页面，但本项目的 FastAPI 开发进程不会自动加载修改：旧版后端可能没有 `/api/campus/login`，提交会返回 `404`，并不代表账号密码错误。页面现在根据健康检查的阶段识别旧后端，禁用登录并提示重启；登录接口的 `404` 和非 JSON 响应也有专门提示。停止原启动终端后重新执行 `python scripts/dev.py`，再刷新网页或点击“重新检查”。

2026-11-01 排障记录：复现默认 `5173 → 8000` 仍连接第二步后端，登录接口返回 404；更新默认服务后，代理健康检查返回 `stage=3`，空登录请求返回预期的本地校验错误 `422 campus_invalid_login`，未发起真实认证请求。前端构建通过，浏览器验证旧版本时显示明确提示并禁用登录，更新后恢复入口，窄屏提示无横向溢出。

从项目根目录运行，不需要启动后端，也不需要安装 Rust 或 `danta-cli`：

```powershell
uv run --frozen python scripts/campus_login.py
uv run --frozen python scripts/check_campus.py --query "图书馆"
```

登录脚本交互读取邮箱与隐藏密码，只发送到固定的 `https://auth.fduhole.com/api/login`。密码不写入文件、不放入命令参数；不能隐藏密码的终端会拒绝继续。仅将返回的 `access` / `refresh` 保存到 `CAMPUS_AUTH_FILE`：先给临时文件设置当前用户权限（Windows 专用 ACL，POSIX `0600`），再写入并原子替换；权限设置失败则不保存。默认 `.private/` 已被 Git 忽略，若自定义路径，也必须自行确保不会进入版本控制或提交包。

`check_campus.py` 使用真实账号直接搜索、读取命中的帖子元数据与楼层，有下一页且预算允许时再检查分页。脚本只输出数量、洞号和状态，不打印正文、邮箱或 token；无结果或无法读取楼层不算联调通过。它默认读取最多 3 页、每页 20 条，且受 90 秒总预算约束。2026-11-01 已使用本项目凭据通过真实搜索、详情和分页检查；下面的 JSON 仍是合成结构示例。

应用只允许五类固定上游接口：登录、刷新、楼层搜索、帖子元数据和帖子楼层。全部业务读取都使用 GET 和 HTTPX 参数编码，不提供任意 URL、发帖、点赞、私信或用户信息接口，不读取任何 CLI 配置。禁用重定向和环境代理。后端提供一个网页登录入口和两个独立读取入口；对话允许树洞时，会将筛选后的楼层内容发送给模型：

| 本地接口 | JSON 请求示例 | 行为 |
| --- | --- | --- |
| `POST /api/campus/login` | `{"email":"synthetic@example.invalid","password":"仅为结构示例"}` | 请求认证接口并安全保存 token；响应仅含成功状态和提示 |
| `POST /api/campus/search` | `{"query":"图书馆","offset":0,"limit":20}` | 请求 `/api/floors/search`，返回一页楼层 |
| `POST /api/campus/thread` | `{"hole_id":12,"offset":0,"limit":20}` | 先请求 `/api/holes/12` 元数据，再请求 `/api/holes/12/floors` |

关键词去除首尾空白，长度 1–500；洞号为正整数，偏移非负，条数默认 20、范围 1–50。拒绝多余参数、字符串形式的数字及布尔值。详情的元数据与楼层必须属于请求的洞号；无效输入返回 `422`，上游格式不符返回 `502 campus_invalid_response`，不会伪装成空结果。

返回 `results` 中仅含 `source=campus`、`hole_id`、`floor_id`、`content`、`time_created`、可空的 `time_updated`、`truncated` 和 `redacted`。剔除匿名昵称、用户标识、投票、嵌套引用等字段及已删除楼层；正文做邮箱和大陆手机号的基础替换，再按配置截断。这不是完整匿名化，仍需把帖子内容当作可能含个人信息的不可信资料。日期必须来自上游且可解析，缺少可选日期时不补造。没有来源 URL，不拼接未经验证的深层链接。详情另含白名单帖子元数据 `thread`，搜索时为 `null`。

分页附 `offset`、`limit`、去重前的 `raw_count`、`next_offset`、`has_more=null`、`complete=false`。满页才提供下一页候选偏移，按原始条数推进；短页和空页停止自动翻页，但服务端普通数组没有总数或明确结束标记，因此不宣称完整遍历。独立 HTTP 请求各读一页，不跨请求保存去重状态；需要多页时，应用内部必须在同一工作流传入共享 `CampusBudget(settings.max_campus_pages)`。相同查询或帖子跨页按洞号/楼层 ID 去重，搜索后读取详情仍保留上下文。失败的分页尝试也占页数，元数据请求、刷新和重试不额外算页。对话 Agent 已把这一预算与工具调用次数、总时长一起执行。

access token 被上游以 `401` 拒绝后，用 refresh token 请求 `POST /api/refresh`，原子保存新的 token 对，再重试原业务请求一次。一个服务实例使用共享刷新锁，等待者重读文件以复用新 token。刷新认证失败或新 access token 仍被拒绝时，明确要求重新登录，同一失效凭据不会反复刷新；登录脚本写入新凭据后，后端下一次请求会重新读取，不必重启。此机制只支持当前单进程服务；不要同时运行多个服务实例、登录和独立检查脚本竞争同一 token 文件。

业务 GET 对网络错误、超时和 `429/502/503/504` 最多重试一次，间隔 1 秒；`Retry-After` 超过 1 秒或为日期时直接报告失败，不提前重试。认证 POST 不自动重试，避免 token 轮换或登录被重复提交。未知上游状态、响应正文、异常细节及凭据都不会透传。

| 错误码 | 含义 |
| --- | --- |
| `campus_invalid_login` / `campus_login_failed` | 登录输入无效 / 邮箱、密码或账号状态未通过认证 |
| `campus_login_required` / `campus_credentials_invalid` | 未登录或本地凭据不可读/无效 |
| `campus_credentials_write_failed` | 无法安全保存凭据，需要检查权限并重新登录 |
| `campus_auth_failed` | 认证失效，需要重新登录 |
| `campus_forbidden` / `campus_not_found` | 无权限 / 帖子或资源不存在 |
| `campus_rate_limited` | 上游限流 |
| `campus_timeout` / `campus_unreachable` | HTTP 超时 / 网络不可达 |
| `campus_invalid_response` / `campus_upstream_error` | 响应契约变化 / 异常 HTTP 状态 |
| `campus_page_budget_exhausted` / `campus_request_budget_exhausted` | 工作流页数预算 / 总时长预算耗尽 |

上述失败不影响已允许的公开网页服务，也不会被当作“没有帖子”。页面已提供跨来源对话、树洞楼层来源卡片、数据源选择与 Skill/计划/结束原因展示。

## 验证

最终事件的 `metrics` 除累计 token 和模型调用次数外，还记录已报告完整用量的调用数 `usage_reported_calls`，以及缓存命中/未命中 token 和 `cache_usage_reported_calls`。缓存明细之和必须等于该调用的输入 token 才计入。缺失用量不代表零费用；模型故障可能产生无法观测的费用。

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

质量评测与接口冒烟分开运行。17 组固定案例均调用真实 DeepSeek，其中 4 组使用真实 Tavily/公开网页，`live_policy` 还使用本项目树洞凭据；其余检索/正文为明确标注的合成情境。新增 `service_scope` 比较不同渠道价格与校区适用性，不针对某所学校硬编码答案。调用产生服务费用；无真实配置时不能把合成结果当作真实验收：

```powershell
uv run --frozen python scripts/evaluate_quality.py --label local-check
uv run --frozen python scripts/evaluate_quality.py --label thinking-check --thinking enabled --case distance
uv run --frozen python scripts/evaluate_quality.py --label conflict-check --case source_conflict --case campus_unavailable
uv run --frozen python scripts/evaluate_quality.py --label no-review-check --review disabled --case source_conflict --case post_injection
uv run --frozen python scripts/evaluate_quality.py --label repair-check --exclude-case distance --exclude-case distance_decoy
uv run --frozen python scripts/evaluate_quality.py --label recovery-repeat --case service_scope --case campus_unavailable --repeat 3
uv run --frozen python scripts/summarize_quality.py .private/quality/local-check.json .private/quality/no-review-check.json
```

报告保存到忽略目录 `.private/quality/`，包含固定问题、回答、证据、调用记录与用量，不保存密钥或思考内容。真实树洞正文及回答中原样复制的正文被移除，只保留来源标识供本地核对；合成帖子可完整复查。合成认证文件使用临时目录，绝不读取真实凭据；同名标签会拒绝覆盖旧结果。脚本采集结果，需人工逐项核对；不会用“接口成功”或引用数量自动判定通过。费用摘要按已观测 token、缓存明细及搜索次数估算，注明定价核对日期、峰谷价范围和计费缺口，不能代替账单。已有前后对比、未成功的中间结果和默认值选择见 [质量验收记录](docs/quality-evaluation.md)。

第五步浏览器演示依次运行：① 自动/允许树洞模式，对照在读证明官方说明与同学经验，再追问“改到枫林校区”；② 新建会话，选择“仅公开网页”，查询研究生院官网；③ 在隔离演示服务验证树洞失效后继续网页回答：

```powershell
npm --prefix frontend run build
uv run --frozen python scripts/demo_failure.py --port 8002
```

打开 `http://127.0.0.1:8002`，页面顶部会明确标注模拟认证失效。模型和网页服务仍是真实调用；树洞登录/刷新/业务请求固定返回合成 401，不会访问真实树洞，也不会读取或覆盖项目凭据。提问“先查树洞江湾图书馆体验；若认证失败，继续查复旦图书馆官网，说明是否取得同学经验”。结束后 Ctrl+C 停止演示，临时合成凭据自动清理。不要在演示页输入真实密码。

2026-11-01 验证记录：

- **自动化模拟验证**：60 项测试通过。覆盖搜索/配置、工具协议、追问历史、会话隔离、清空/删除、参数校验、预算、上游错误与取消清理；补充候选答案修正、补查与去重、未知引用阻断、思考协议及用量、独立超时、网页读取地址限制/DNS 固定/重定向/截断/错误脱敏，以及核对阶段取消后不提交历史。测试不读取本地凭据、不访问外网；有一条依赖库 TestClient 的弃用提示，不影响结果。
- **构建与启动验证**：TypeScript 检查与生产构建通过；无 `.env`、无树洞凭据启动前后端与代理检查通过。开发启动不导入或执行 Rust / `danta-cli`，不依赖参考仓库。
- **浏览器验证**：第一步工作台检查保留；第二步桌面与窄屏对话、工具进度、真实来源展开、追问条件、刷新恢复会话、停止回答、清空历史与来源通过。验收截图在本地忽略目录 `.private/verification/`。
- **Tavily 真实服务验证（通过）**：用户完成本地配置后，`python scripts/check_search.py` 查询“复旦大学 官方网站”，返回 5 条真实结果。随后在浏览器查询 `site.fudan.edu.cn 在读证明 办理`，再次返回 5 条结果，页面显示实际来源链接、服务提供的日期及“日期未知”。已打开并核对其中的[复旦大学研究生院](https://gs.fudan.edu.cn/)来源，标题与页面内容一致。两次请求均使用实际 Tavily API，未使用模拟响应，未调用模型。
- **检索质量观察**：真实返回同时包含较旧资料、校外转载和其他学校页面。关键词中的 `site:` 不应视为应用强制执行的域名过滤；后续 Agent 必须核对实际域名、相关性与时效性，不能直接将所有命中视为有效办事依据。本次只验收搜索接入及展示，不认定办事要求已核实。
- **DeepSeek + Tavily 真实服务验证（通过）**：2026-11-01 执行 `python scripts/check_chat.py`，`deepseek-flash` 实际调用 `search_web`，Tavily 返回 5 条真实来源（包含 `https://gs.fudan.edu.cn/`），模型按来源编号回答；后续不搜索的追问保留了“江湾”条件。浏览器另做一次真实检索和追问，通过事件流显示结果。浏览器中也在搜索进行时停止请求，未完成轮次未留入历史，随后清空成功。此记录验收调用链，不代表摘要内的所有事实都已人工核实。
- **第二步补充验证**：固定 10 组案例的基线、失败中间结果和最终逐项记录见质量报告；最终记录包括修复后的定向复测，不代表单次全量通过。真实官网查询、正文读取及条件追问通过；距离题最后一次未查明里程，只通过证据边界检查。浏览器验证核对进度、回答引用与累计来源分组、已读正文标记，390px 窄屏无横向溢出，控制台无错误。
- **第三步模拟验证**：108 项测试全部通过（新增 48 项、原有 60 项回归）。覆盖登录与原子凭据保存、Windows 当前用户 ACL、参数编码、分页去重与跨来源上下文、截断及敏感字段过滤、无结果、并发 401 仅刷新一次、失效后重新登录、403/404/429/临时故障/超时/格式变化、端点白名单、总预算与取消清理；网页登录补充成功、失败保留旧凭据、非法参数和错误 JSON 不回显秘密、凭据不进入会话历史等测试。未访问真实树洞服务。
- **第三步构建与界面验证**：前端类型检查与构建通过，前后端及代理冒烟在临时端口 `8002/5175` 通过（原有 `8000` 服务保持运行）。浏览器使用独立合成认证服务验证登录成功、失败提示、提交后密码清空及状态刷新；390px 窄屏无横向溢出。Windows 在项目 E 盘目录实际验证了仅当前用户访问的凭据写入，避免依赖修改文件所有者的权限。截图保存在 `.private/verification/campus-login-desktop.png` 和 `campus-login-mobile.png`，合成凭据与真实默认凭据隔离。
- **第四步验证**：123 项模拟测试通过，前端构建及 Skill 校验通过。真实树洞搜索取得 20 条结果、命中帖子读取 18 层并验证下一页，共 3 页；真实跨来源对话执行计划、网页搜索、树洞搜索和帖子读取，返回 W/C 引用，随后仅网页追问保留枫林条件。详情见 [第四步验收记录](docs/stage4-verification.md)。
- **未验证项**：真实 access token 过期后的刷新尚未主动触发；刷新轮换、并发及失败重登录由模拟测试验证。工程调用链通过不等于每次回答质量通过，保留距离题命中和表述稳定性的限制。

## 目录

```text
frontend/                 React + TypeScript 工作台
backend/app/              FastAPI、会话、Agent、网页与树洞只读适配器、凭据管理
skills/campus-research/   已加载的校园调研 Skill
tests/                    隔离真实凭据的模拟测试
scripts/                  安装、启动、独立树洞登录与真实服务验收脚本
.env.example              不含真实密钥的配置示例
pyproject.toml / uv.lock   Python 依赖与锁文件
```

后续范围见 [plan.md](plan.md)。第五步检查和演示已执行，质量未通过项如实保留；第六步实验报告和交付尚未实施。
`npm run build` 当前验证静态前端可构建；`vite preview` 不提供后端代理，日常运行请使用上述开发启动入口。

本地 `.env`、`.private/`、依赖、日志与构建目录均由 `.gitignore` 排除。后续提交压缩包时同样需要排除这些目录及 `.git`。
