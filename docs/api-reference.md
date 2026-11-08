# Ask Danta 接口与配置参考

## 环境变量

应用启动时读取环境变量及 `.env`，再叠加 `.private/settings.json` 中通过设置页保存的字段。设置页保存后立即生效；端口、认证和历史文件路径仍通过环境变量配置，需重启。页面保存过的字段优先于环境变量；未保存的字段继续沿用环境配置。

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
| `SESSION_DB_FILE` | `.private/history/chat.sqlite3` | 本机聊天记录；使用独立私有目录，数据库与事务文件不进入提交包 |
| `CAMPUS_MAX_CONTENT_CHARS` | `4000` | 每条树洞正文最多 100–12000 字符，截断有标记 |
| `HTTP_TIMEOUT_SECONDS` | `15` | 树洞 HTTP 超时及搜索/网页读取的默认超时；模型使用独立配置 |
| `MAX_TOOL_CALLS` | `12` | 每轮用户请求最多尝试的工具调用数；无效参数和未知工具也计数，已耗尽树洞额度的本地拦截另计 |
| `MAX_CAMPUS_PAGES` | `8` | 同一树洞工作流共享的分页尝试预算；独立 HTTP 入口一次读取一页 |
| `REQUEST_BUDGET_SECONDS` | `150` | 单轮 Agent 总时长，包含检索与最终回答 |
| `BACKEND_PORT` | `8000` | 后端端口，1024–65535 |
| `FRONTEND_PORT` | `5173` | 前端端口，1024–65535，须与后端不同 |

## 健康检查与网页搜索

`GET /api/settings` 返回可编辑配置及 `model_api_key_configured`／`search_api_key_configured`，不返回密钥。`PATCH /api/settings` 只更新请求中出现的字段；省略密钥表示保留，空字符串表示清除。支持上述模型、搜索、答案核对与预算参数，不支持修改端口或文件路径。响应禁止缓存，参数错误不会回显输入；写入失败保持旧配置，有会话正在回答时返回 `409`。设置以当前用户可访问的权限原子写入本机私有文件，不能用于多用户远程部署。

`GET /api/health` 返回 `stage=6`、运行状态、非敏感配置状态和预算。`status=ok` 只代表本地后端存活；`model.chat_enabled` 表示已配置可发起对话。`model.available` 与 `campus.available` 保持 `false`（健康检查不验证远端可用性）；`campus.credentials_present` 仅表示文件存在；`auth_state` 为 `missing/invalid/expired/configured`，`tools_enabled` 代表本地凭据可用于尝试调用，不保证远端仍有效。`skills` 列出已加载的 `campus-research`。

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

## 会话与事件流

| 接口 | 用途 |
| --- | --- |
| `POST /api/sessions` | 新建会话，返回 `session_id`、空历史与来源 |
| `GET /api/sessions` | 按最近活动排序的会话摘要；未提问的空白会话不出现在列表中 |
| `GET /api/sessions/{session_id}` | 读取已完成的用户/助手消息、来源与忙碌状态 |
| `PATCH /api/sessions/{session_id}` | 修改 `title`（1–80 字符）或 `source_preference`（`auto/web/all`） |
| `POST /api/sessions/{session_id}/fork` | 以 `message_index` 指定用户消息位置，提供 `expected_message_count` 校验会话未变；创建只包含该消息之前上下文的新会话，保留原会话 |
| `POST /api/sessions/{session_id}/clear` | 清空历史、用户条件与检索来源，保留会话 ID |
| `DELETE /api/sessions/{session_id}` | 删除会话 |
| `POST /api/sessions/{session_id}/cancel` | 主动取消当前回答，返回 202；读取会话确认 `busy=false` 后可切换或删除 |
| `POST /api/sessions/{session_id}/chat` | 请求体 `{"message":"你的问题","source_mode":"web","source_preference":"auto"}`，返回 SSE 事件流；`source_mode` 是本轮有效权限，`source_preference` 是供下次恢复的用户偏好 |

问题去除首尾空白，限 1–8000 字符。无效输入返回 `422`；不存在的会话返回 `404`；同一会话正在回答时，重复发送、清空或删除返回 `409`；未配置模型返回 `503 model_not_configured`。流建立前的错误为 JSON，流中的上游失败通过 `error`/`tool_error` 事件报告。

前端使用 `fetch` 读取 POST 响应体，每帧格式为 `data: {JSON}\n\n`。事件包括：

- `start`、`model_start`：本轮开始与模型工作状态。
- 状态变化事件额外携带 `progress` 字段（不改变原有事件顺序）：供界面展示的执行记录快照，含 `started_at`（Unix 毫秒）、`elapsed_ms`、`status` 和 `steps`。步骤含固定中文 `label`、状态、相对开始时间、完成耗时，以及工具名与调用 ID；结果摘要仅保留数量／读取完成状态，不保存原始参数、正文或内部思考。会话 GET 的 `progress` 支持刷新后轮询恢复，最终 `message.progress` 随回答持久化。旧消息没有该字段时仍正常展示。停止后当前记录标记为 `interrupted`，不会添加伪造回答。
- `tool_start`：调用 ID 和工具名；`tool_complete`：同一 ID 和工具结果，搜索返回 `query/results`，读取返回 `source_id/url/title/text/truncated`；`tool_error`：同一 ID 和脱敏错误。
- `review_start`：正在核对候选答案，候选文本不展示、不写入历史；核对可在原预算内触发补查。
- `budget`：停止进一步检索的原因；`error`：模型或总预算失败。
- `final`：`message` 含最终文本、仅引用的 `sources`、警告、`limited`、`reviewed` 与 `status`；另附全部 `session_sources`、实际尝试的 `tool_calls`，以及 `metrics` 中的模型调用次数、上游可取得的 token 用量和耗时。`status=incomplete` 表示预算或故障等导致未完成；`complete` 仅表示完成回答流程，不是事实正确性的评分。

## 树洞认证与只读接口

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
