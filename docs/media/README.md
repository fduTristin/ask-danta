# 产品演示素材

- `ask-danta-demo.mp4`：1920 × 1080、30 fps、H.264，带画面字幕的无声产品演示。
- `ask-danta-preview.gif`：8 秒循环预览，供项目 README 展示。
- `ask-danta-poster.png`：静态封面，可用于介绍页面或分享。

视频通过浏览器操作当前 React 界面录制，展示搜索范围、执行记录、引用片段、树洞配图、追问与历史菜单。模型、网页搜索、树洞接口均由隔离的演示服务提供合成响应；回复时长为演示安排，不代表真实服务速度。没有录制个人聊天、密码、访问令牌或真实树洞帖子。

片中配图是项目为演示绘制的示意图。旦挞 Logo 及品牌来源说明见[项目 README](../../README.md#项目来源与致谢)。本视频没有配音或背景音乐。

## 重新录制

先按项目 README 安装 Python 和前端依赖，准备系统 Chrome，并确保本机 8008、5178 端口空闲。录制不会连接已有的开发服务，也不会访问真实模型或校园 API。

```sh
node frontend/node_modules/@playwright/test/cli.js install ffmpeg
node scripts/record_promo.mjs
python scripts/export_promo.py --ffmpeg /path/to/ffmpeg
```

最后一步需要支持 `libx264` 的完整 FFmpeg；Playwright 自带的精简版本仅用于原始录制。也可将 `imageio-ffmpeg` 安装到被忽略的 `.private/video-tools`，导出脚本会自动寻找其中的 Windows FFmpeg：

```sh
python -m pip install --target .private/video-tools imageio-ffmpeg
python scripts/export_promo.py
```

原始 WebM、章节时间表和验收接触表保存在 `.private/promo/`，不进入版本库。导出时仅更新本目录的三个成品文件；再次录制前请先保存需要保留的旧成品。
