# Ask Danta · 问问旦挞

Ask Danta 是面向复旦大学校园场景的检索问答应用，支持公开网页检索与树洞资料检索，为校园办事、课程学习和校园生活问题提供带来源引用的回答。应用在本机运行，支持多轮追问和本地会话管理。

[下载安装包](https://github.com/fduTristin/ask-danta/releases/latest) · [1.0.1 发布说明](docs/releases/v1.0.1.md) · [问题反馈](https://github.com/fduTristin/ask-danta/issues)

## 开始使用

### 桌面安装

从 [GitHub Releases](https://github.com/fduTristin/ask-danta/releases/latest) 下载适合系统与架构的安装包。安装包包含运行环境，无需另装 Python、Node.js 或 uv。

| 平台 | 安装文件 |
| --- | --- |
| Windows x64 | `.exe` |
| macOS Apple Silicon（arm64） | `.dmg`，另提供 `.zip` |
| macOS Intel（x64） | `.dmg`，另提供 `.zip` |
| Linux x64 | `.AppImage` 或 `.deb`；AppImage 运行环境需要 FUSE |

当前安装包未使用开发者证书签名，macOS 使用 ad-hoc 签名，可能出现 SmartScreen 或 Gatekeeper 提示。当前不支持自动更新；升级前请退出应用，再安装新版本。桌面版数据位置见[桌面构建与发布](docs/desktop.md#数据位置)。

### 配置服务

1. 启动后打开侧栏底部的“设置”，填写模型接口地址、模型名称和 API Key。
2. 如需真实网页搜索，在“网页搜索”中选择 Tavily 并填写 Tavily API Key。默认搜索使用明确标记的合成样例，不能作为真实资料；该模式仍需配置模型服务。
3. 如需树洞检索，在“设置 → 账号 → 登录树洞”登录。树洞功能需要具备相应社区访问权限，并遵守社区规则；未登录也可使用仅网页模式。

模型和搜索服务可能产生费用，取决于所用服务及账户额度。应用会将问题、相关对话上下文和检索材料发送至所配置的模型服务；启用 Tavily 时，检索词会发送至 Tavily。详见[数据管理与使用边界](#数据管理与使用边界)。

## 项目演示

[![Ask Danta 产品演示](docs/media/ask-danta-preview.gif)](docs/media/ask-danta-demo.mp4)

[观看完整视频](docs/media/ask-danta-demo.mp4) · 约 35 秒 · 1080p · 界面操作录屏

演示涵盖数据源选择、执行记录、引用查证、树洞配图、多轮追问及会话管理。视频录制自实际界面，使用合成资料；示例内容及响应时长不代表真实校园信息或服务性能。素材与复现方法见[演示说明](docs/media/README.md)。

## 主要功能

| 功能 | 说明 |
| --- | --- |
| 多源检索 | 搜索公开网页并读取正文；登录后可在访问权限范围内搜索树洞、读取帖子上下文和查看配图。 |
| 数据源选择 | 提供“自动选择”“仅网页”“网页 + 树洞”三种模式；仅网页模式排除先前对话中的树洞证据。 |
| 来源引用与核对 | 回答附有网页与树洞来源，可展开查看摘要、链接、日期和截断提示；默认启用答案核对与修订。 |
| 执行过程 | 显示检索、读取和核对等步骤、工具状态与耗时，支持停止当前请求。 |
| 多轮问答 | 支持追问、复制和失败重试；编辑历史问题会替换该轮及后续内容，提交前提示替换范围。 |
| 本地会话 | 保存消息、引用和执行记录，支持会话新建、切换、重命名和删除；不同会话可同时生成，停止按钮仅作用于当前会话。 |

## 从源码运行

需要 Python 3.11+、[uv](https://docs.astral.sh/uv/getting-started/installation/)、Node.js 22.12+ 和 npm。下载或克隆仓库后，在项目根目录执行：

```sh
python scripts/setup.py
python scripts/dev.py
```

打开 [http://127.0.0.1:5173](http://127.0.0.1:5173)，按上方说明配置服务。API 文档位于 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。前后端默认仅监听本机回环地址；使用 `Ctrl+C` 停止服务。

安装脚本使用锁定的依赖版本；模型、搜索和回答参数通过设置页管理，无需创建 `.env`。源码浏览器开发支持 Vite 热更新。自行构建桌面安装包见[桌面构建与发布](docs/desktop.md#本地开发与构建)。

## 配置说明

设置保存后生效，无需重启应用；有回答正在生成时，需等待完成或停止后再保存。API Key 输入框留空保留原值，“清除”操作在保存后生效。设置接口不返回密钥原文，界面仅显示是否已配置。

| 配置项 | 默认值 | 用途 |
| --- | --- | --- |
| 接口地址 | `https://api.deepseek.com` | 模型服务接口地址。 |
| 模型名称 | `deepseek-flash` | 对话与工具调用使用的模型名称。 |
| 模型 API Key | 空 | 需自行填写模型服务密钥。 |
| 搜索服务 | 合成样例 | 选择 Tavily 并配置密钥后启用真实网页搜索。 |
| 答案核对 | 开启 | 核对答案与证据，并按需修订。 |

“高级”设置可调整思考选项、超时、输出长度与执行预算。已有设置不会随程序默认值更新而自动覆盖。完整参数、环境变量和旧配置迁移说明见[接口与配置参考](docs/api-reference.md)。

源码运行时，也可使用交互式脚本登录树洞：

```sh
uv run --frozen python scripts/campus_login.py
```

## 数据管理与使用边界

应用面向单用户本地使用，未提供多用户账号体系或跨设备同步。以下文件路径以数据目录为基准：源码运行使用仓库的 `.private/`，桌面版使用[系统用户数据目录下的 `.private/`](docs/desktop.md#数据位置)。

| 数据 | 保存位置或处理方式 |
| --- | --- |
| 会话记录 | `history/chat.sqlite3`，保存消息、必要引用片段与执行记录。 |
| 树洞凭据 | `campus-tokens.json`，与会话记录分开保存。 |
| 服务配置与密钥 | `settings.json`，以本地 JSON 文件保存；程序设置文件访问权限，不对密钥另行加密。 |
| 模型输入 | 问题、相关会话上下文及回答所需的检索材料发送至已配置的模型服务。 |
| 网页搜索 | 启用 Tavily 时，检索词发送至 Tavily。 |
| 树洞配图 | 展开来源后，由浏览器按需请求 `image.fduhole.com` 图床，不发送当前页面的 Referer。 |

`.private/`、`.env` 及本地凭据和历史数据不纳入版本控制。桌面升级保留既有设置与会话，源码开发数据不会自动迁入桌面版。首次启用树洞检索时，界面会提示相关资料将发送至模型服务。

树洞帖子反映发帖者的个人经验，正式政策和办事要求应以学校发布的信息为准。来源引用与自动核对不能保证回答正确；资料截断、来源不可用或核对失败时，界面会显示相应提示。

## 技术架构与开发

前端使用 React、TypeScript 和 Vite，通过 HTTP 管理会话、通过 SSE 接收执行事件。后端使用 FastAPI、HTTPX 和 Pydantic，负责模型调用、检索工具、认证与数据校验；会话使用 SQLite 持久化。桌面端使用 Electron 与 PyInstaller 打包。

Agent 在时间、工具调用次数和分页预算内检索并读取资料，再生成答案；启用核对时，正文在核对完成后展示。校园调研策略见 [ask-danta-research Skill](skills/ask-danta-research/SKILL.md)。

```text
backend/app/              后端接口、Agent、模型与数据源适配器
frontend/src/             前端页面、交互组件与样式
frontend/e2e/             浏览器端回归测试
tests/                    后端及适配器测试
desktop/                  桌面入口与打包配置
skills/ask-danta-research/ 校园调研策略
scripts/                  安装、启动、验证与演示录制脚本
docs/                     接口、构建、发布和验证文档
```

在项目根目录运行：

```sh
# 后端测试
uv run --frozen pytest -q

# TypeScript 检查与前端构建
npm --prefix frontend run build

# 浏览器回归测试
npm --prefix frontend run test:e2e
```

自动化测试使用合成响应，不依赖真实模型或校园账号。浏览器测试默认使用本机 Chrome，并在 `8006`、`5176` 端口启动独立测试服务。真实服务联调会访问对应服务，并可能消耗额度；运行条件见[开发计划与验证记录](plan.md)。答案核对的性能对照见[核对速度验证](docs/review-speed-verification.md)。

## 反馈与贡献

通过 [GitHub Issues](https://github.com/fduTristin/ask-danta/issues) 报告问题或提出建议。问题报告请附应用版本、系统与架构、复现步骤和已脱敏的错误信息，不要提交 API Key、登录凭据或未经处理的私人会话与树洞内容。

欢迎提交 Pull Request。请说明改动用途、影响范围和验证结果；界面变更请附截图。开发约定见 [AGENTS.md](AGENTS.md)。

## 项目来源与致谢

旦挞校园助手由[旦夕开发组（DanXi-Dev）](https://github.com/DanXi-Dev)开发，旦挞茶楼为团队开发和运营的校内匿名社区，本项目界面中简称“树洞”。

应用图标使用[旦挞校园助手](https://danxi.fduhole.com/project/app)的猫咪 Logo，[原图来源](https://danxi.fduhole.com/assets/app.webp)为旦挞官网。使用树洞功能须遵守[旦挞社区服务使用协议](https://danxi.fduhole.com/doc/community-user-agreement)及相应访问权限要求。

## 许可证

本项目代码与文档采用 [MIT License](LICENSE)。第三方依赖遵循各自的许可证；旦挞名称、Logo 等品牌素材不包含在本项目的 MIT 许可范围内。代码许可不授予树洞数据的访问或再分发权限。
