# Ask Danta（问问旦挞）

问问旦挞是面向复旦师生的校园问答工具，也是基于旦挞校园服务独立开发的衍生应用。查询办事流程时，它可以从公开网页查找学校通知。了解一门课的作业量、食堂的菜品或科研项目的参与体验时，它可以在获得许可后检索旦挞茶楼（树洞）的讨论。每条回答都可以继续追问，有引用的结论可以展开查看依据。

## 项目与图标来源

旦挞校园助手由 **旦夕开发组（DanXi-Dev）** 开发。本项目使用的 Logo 取自该团队在旦挞官网发布的校园助手图标。[开发组主页](https://github.com/DanXi-Dev) · [旦挞校园助手](https://danxi.fduhole.com/project/app) · [Logo 原图](https://danxi.fduhole.com/assets/app.webp)

旦挞茶楼是由旦挞团队开发和运营的校内匿名社区，在问问旦挞的界面中简称“树洞”。依据社区使用协议，通过第三方客户端访问社区服务须获得管理团队的明确许可。[旦挞社区服务使用协议](https://danxi.fduhole.com/doc/community-user-agreement)

## 本地运行

准备 Python 3.11 或更高版本、[uv](https://docs.astral.sh/uv/getting-started/installation/) 和 Node.js 22.12 或更高版本（含 npm）。在项目根目录安装依赖。

```sh
python scripts/setup.py
```

首次安装会从 [.env.example](.env.example) 创建 `.env`。在其中填写 `MODEL_API_KEY` 即可启用对话。要检索真实网页，还需将 `SEARCH_PROVIDER` 设为 `tavily` 并填写 `SEARCH_API_KEY`。默认的 `mock` 模式仅为网页搜索提供明确标记的示例结果。

```dotenv
MODEL_API_KEY=你的_DeepSeek_API_密钥
SEARCH_PROVIDER=tavily
SEARCH_API_KEY=你的_Tavily_API_密钥
```

启动应用后，在浏览器打开 [问问旦挞](http://127.0.0.1:5173)。

```sh
python scripts/dev.py
```

前后端默认只监听本机地址。按 Ctrl+C 可关闭服务。修改 `.env` 后重新启动即可应用配置。

## 提问与查证

- **选择搜索范围。** 输入框旁的菜单提供“自动选择”“仅网页”和“网页 + 树洞”。查询通知、日期或办理材料时可选“仅网页”。获得社区访问许可后，可在“设置 → 树洞账号”登录并启用树洞。自动模式依据登录状态选择可用来源。
- **查看回答依据。** 点击 `[W1]` 这类引用可查看网页标题、链接及摘要，点击 `[C1]` 可查看对应的树洞楼层片段和日期。引用兼容模型输出的小写编号（如 `[c1]`），界面统一显示大写标签；旧回答漏掉的关联会从同一会话保留的真实资料恢复。比较课程或项目体验时，可以据此分辨不同年份、不同参与者的反馈。
- **查看回答进度。** 等待时实时显示当前执行步骤和耗时，点击可展开网页搜索、资料读取、答案核对等记录，以及工具返回的资料数量和失败状态。完成后记录默认收起，随回答保存在本机；刷新仍可查看。记录只包含执行状态，不包含模型内部思考、工具原始参数或原始结果。回答正文仍在核对完成后一次显示。
- **继续对话。** 在同一会话中补充校区、时间或身份，助手会结合前文回答。侧栏支持新建、切换、重命名和删除会话。生成过程中可随时停止。

## 数据与隐私

应用以单用户方式在本机运行。聊天记录和引用片段保存在 `.private/history/chat.sqlite3`，树洞登录凭据单独保存在 `.private/campus-tokens.json`。模型服务会收到回答所需的问题、相关对话和检索材料。启用树洞前，界面会提示相关帖子片段将发送给模型。使用 Tavily 时，网页检索词会发送给 Tavily。

## 开发与测试

前端使用 React、TypeScript 和 Vite，后端使用 FastAPI、HTTPX 和 SQLite。校园调研规则位于 [campus-research](skills/campus-research/SKILL.md)。接口参数、流式事件和检索额度见[接口与配置参考](docs/api-reference.md)。服务启动后也可查看本机 [API 文档](http://127.0.0.1:8000/docs)。

```sh
uv run --frozen pytest -q
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

后端和浏览器测试使用模拟服务。浏览器测试默认调用本机 Chrome，并在端口 8006 和 5176 启动独立的测试服务。
