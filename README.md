# 校内信息研究助手 · Campus Agent

面向本机单用户的校园信息调研应用，采用 React + TypeScript + Vite、FastAPI + HTTPX。
本次实现 [开发计划](plan.md) 的**第一步：建立项目与配置**。当前页面可检查配置状态并试用搜索；尚未实现聊天、Agent 循环、会话记忆、树洞登录或 Skill 加载。

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
| `MODEL_NAME` | `deepseek-flash` | 可修改的模型名；第一步只配置、不调用 |
| `MODEL_API_KEY` | 空 | DeepSeek API Key |
| `SEARCH_PROVIDER` | `mock` | `mock` 为离线样例；`tavily` 为真实搜索 |
| `SEARCH_API_KEY` | 空 | Tavily API Key |
| `SEARCH_MAX_RESULTS` | `5` | 单次最多 1–10 条结果 |
| `SEARCH_MAX_SNIPPET_CHARS` | `2000` | 每条摘要最多 100–10000 个字符，截断有标记 |
| `CAMPUS_AUTH_FILE` | `.private/campus-tokens.json` | 为第三步预留；当前只检测文件是否存在，不读取内容 |
| `HTTP_TIMEOUT_SECONDS` | `15` | 搜索 HTTP 超时及请求整体截止时间 |
| `MAX_TOOL_CALLS` | `6` | 第二步 Agent 工具调用上限，当前仅配置 |
| `MAX_CAMPUS_PAGES` | `3` | 第三步校内检索分页预算，当前仅配置 |
| `REQUEST_BUDGET_SECONDS` | `90` | 第二步单轮 Agent 总时长，当前仅配置 |
| `BACKEND_PORT` | `8000` | 后端端口，1024–65535 |
| `FRONTEND_PORT` | `5173` | 前端端口，1024–65535，须与后端不同 |

模型默认值依据 [DeepSeek 官方 API 文档](https://api-docs.deepseek.com/)（2026-11-01 核对）。密钥存在只代表“已配置”，不代表模型可用或已完成真实调用。

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

`GET /api/health` 返回运行状态、非敏感配置状态和预算。`status=ok` 只代表本地后端存活；`model.available`、`campus.available` 当前始终为 `false`。

`POST /api/search` 是第一步的独立搜索验证入口，第二步再注册为 Agent 工具。请求：

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
# 自定义端口时：python scripts/check_search.py --port 8001
```

脚本拒绝把 mock 结果记为真实验收通过，只输出提供商、数量及来源 URL。也应在页面手动搜索并打开来源，核对标题、摘要和相关性。

2026-11-01 验证记录：

- **自动化模拟验证**：22 项测试通过，覆盖无凭据启动、样例不联网、配置优先级、预算校验、参数校验、统一结果、去重与截断、日期缺失、空结果、认证失败、限流、超时、网络失败、无效响应及错误脱敏。
- **构建与启动验证**：TypeScript 检查与生产构建通过；无 `.env`、无树洞凭据启动前后端与代理检查通过。开发启动不导入或执行 Rust / `danta-cli`，不依赖参考仓库。
- **浏览器验证**：桌面与窄屏工作台、健康状态、离线搜索结果及空白关键词禁用通过。
- **Tavily 真实服务验证（通过）**：用户完成本地配置后，`python scripts/check_search.py` 查询“复旦大学 官方网站”，返回 5 条真实结果。随后在浏览器查询 `site.fudan.edu.cn 在读证明 办理`，再次返回 5 条结果，页面显示实际来源链接、服务提供的日期及“日期未知”。已打开并核对其中的[复旦大学研究生院](https://gs.fudan.edu.cn/)来源，标题与页面内容一致。两次请求均使用实际 Tavily API，未使用模拟响应，未调用模型。
- **检索质量观察**：真实返回同时包含较旧资料、校外转载和其他学校页面。关键词中的 `site:` 不应视为应用强制执行的域名过滤；后续 Agent 必须核对实际域名、相关性与时效性，不能直接将所有命中视为有效办事依据。本次只验收搜索接入及展示，不认定办事要求已核实。
- **尚未执行的真实服务验证**：DeepSeek 模型调用与树洞接口联调，分别留在第二步和第三步。

## 目录

```text
frontend/                 React + TypeScript 工作台
backend/app/              FastAPI、配置与网页搜索适配器
skills/campus-research/   Skill 预留目录，第四步实现与加载
tests/                    隔离真实凭据的模拟测试
scripts/                  安装、启动与真实搜索验收脚本
.env.example              不含真实密钥的配置示例
pyproject.toml / uv.lock   Python 依赖与锁文件
```

后续范围见 [plan.md](plan.md)。模型调用和短期记忆在第二步，树洞独立登录在第三步，Skill 加载和正式对话交互在第四步。
`npm run build` 当前验证静态前端可构建；`vite preview` 不提供后端代理，日常运行请使用上述开发启动入口。

本地 `.env`、`.private/`、依赖、日志与构建目录均由 `.gitignore` 排除。后续提交压缩包时同样需要排除这些目录及 `.git`。
