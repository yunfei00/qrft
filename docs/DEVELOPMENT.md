# 开发

Python 3.12 + uv；所有源码在 `src/qrft/`，测试在 `tests/`。

```powershell
uv sync --locked --all-extras --group dev
uv run --no-sync ruff format --check .
uv run --no-sync ruff check .
uv run --no-sync pytest -q
```

编码依赖在 `encoder` extra；桌面解码、后台进程和识别依赖在 `decoder` extra；独立调度中心依赖在 `control` extra。测试使用真实二维码、合成 AVI、HTTP、SQLite 和 Qt 控件验证完整流程；合成视频不等于实际屏幕录制。

协议只修改 `core/protocol.py`，不得在编码器、解码器中复制帧格式。分块参数默认 2100，可配置；START 与后续包长度必须一致。目录源、补传、缺包、冲突和完整文件哈希需要一起验证。

## Windows 打包

```powershell
uv run --no-sync python scripts/build_windows.py
uv run --no-sync python scripts/windows_smoke.py
```

输出在 `dist/QRFT-Encoder-CLI`、`dist/QRFT-Decoder`、`dist/QRFT-Control`。编码 EXE 为 console；Decoder 默认打开桌面界面，并提供显式 `worker`、`control` 子命令供进程管理。调度中心启动后在浏览器访问 8787 端口。

CI 只有代码检查、测试和统一三程序构建两个流程。每次交付保留完整 onedir 目录及核心文档；不提交构建输出、录屏、数据库、临时证据或真实 Token。
