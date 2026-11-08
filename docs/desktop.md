# 桌面构建与发布

桌面版由 Electron 管理窗口和后端生命周期，PyInstaller 将 Python 解释器、后端依赖、前端构建结果和校园调研 Skill 打包在一起。后端绑定随机回环端口，仅接受 Electron 注入的随机会话凭证；退出窗口后停止后端。外部 HTTP/HTTPS 链接交给系统浏览器，页面不开放 Node.js 权限。

## 本地开发与构建

使用 Python 3.11+、uv、Node.js 22.12+ 和 npm。在仓库根目录执行 `python scripts/setup.py`、`npm ci` 和 `uv sync --frozen --group desktop` 安装依赖。

| 命令 | 用途 |
| --- | --- |
| `npm run dev` | 原有浏览器开发模式，前端热更新。也可继续使用 `python scripts/dev.py`。 |
| `npm run desktop:dev` | 构建前端，使用源码后端启动 Electron；修改代码后重新运行。 |
| `npm run desktop:pack` | 构建前后端并生成当前平台的解包应用。 |
| `npm run desktop:dist` | 构建当前平台安装包，输出到 `release/`。 |
| `npm run desktop:smoke` | 使用临时用户目录验证源码 Electron 启动、页面及设置 API，完成后退出。需先构建前端。 |
| `uv run --frozen python scripts/check_desktop.py` | 验证已构建的独立后端、静态资源、访问限制及退出行为。 |

Python 后端须在目标系统和目标架构上构建。不要在 Windows 构建后直接指定 `--mac` 或 `--linux`，否则会带入错误平台的后端。GitHub Actions 使用独立原生 runner 构建 Windows x64（NSIS EXE）、Linux x64（AppImage、deb）、macOS Intel x64 与 Apple Silicon arm64（DMG、ZIP）。Linux AppImage 运行环境需要 FUSE；也可使用 deb。

## 数据位置

本机网络若无法下载 GitHub 的 Electron 二进制，可在当前终端临时设置 `ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/` 和 `ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/` 后重试。Electron 安装失败时运行 `npx install-electron`；已安装的 Electron 可通过 `npx electron-builder --publish never --config.electronDist=node_modules/electron/dist` 复用（先运行 `npm run build`）。镜像为第三方下载来源，Electron 下载仍使用包内校验和；这些设置不写入仓库或全局环境。

桌面数据保存在 Electron `userData` 下的 `.private/`，包括 `settings.json`、`campus-tokens.json` 和 `history/chat.sqlite3`。默认目录为：

- Windows：`%APPDATA%/ask-danta/.private/`
- macOS：`~/Library/Application Support/ask-danta/.private/`
- Linux：`~/.config/ask-danta/.private/`（受 XDG 配置影响）。

源码浏览器开发仍使用仓库的 `.private/`。桌面版不自动导入开发凭据或会话。需要迁移时先退出两端应用，再将开发 `.private/` 的内容复制到桌面数据目录。安装升级保留用户数据，安装包不包含本地密钥、会话、`.env` 或源码开发依赖。

## GitHub Actions 与 Release

工作流位于 `.github/workflows/release.yml`。推送到 GitHub 后，可在 Actions 中手动运行 **Desktop release**，仅生成可下载的构建 artifacts。推送 `v*` 标签会在四个构建任务全部成功后创建 GitHub Release 草稿并上传安装包；确认后在 GitHub 发布草稿。工作流使用仓库自带的 `GITHUB_TOKEN`，无需提供个人访问令牌。

发布版本须与根目录 `package.json` 的 `version` 一致。例如当前版本：

```sh
git push origin HEAD
git tag v0.1.0
git push origin v0.1.0
```

发布后不要移动标签。后续版本先更新根目录版本与 npm 锁文件、提交，再推送新标签。手动构建不创建 Release。构建任务只有读取权限，Release 任务单独授予 `contents: write`；仓库或组织设置必须允许 Actions 运行及该权限。

## 签名与发布资料

当前配置未使用开发者证书签名，macOS 使用临时 ad-hoc 签名。Windows 可能出现未知发布者或 SmartScreen 提示，macOS 下载包可能被 Gatekeeper 拦截；面向公开用户正式分发前建议配置签名与 macOS 公证。本项目尚未接入自动更新。

应用名称暂定 Ask Danta，标识为 `io.github.fdutristin.askdanta`，版本为 `0.1.0`。应用图标使用 `frontend/public/danta-logo.webp`，转换后的 ICO、ICNS 和 PNG 保存在 `desktop/icons/` 并随源码提交，供本地与 Actions 构建使用。替换 logo 后运行 `uv run --with pillow==12.2.0 python scripts/build_icons.py` 重新生成图标。桌面启动时关闭 Electron 默认菜单；macOS 额外保留常用编辑、退出与关闭窗口快捷键。

若需签名，请提供证书类型及 Apple Developer 团队信息，证书和密码应存入 GitHub Secrets，不要提交到仓库或发送到聊天。接入签名时须调整当前关闭签名的构建配置并配置相应 Secrets。

安全配置参考 [Electron 安全指南](https://www.electronjs.org/docs/latest/tutorial/security)，运行器选择参考 [GitHub runner images](https://github.com/actions/runner-images)。
