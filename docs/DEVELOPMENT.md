# QRFT 开发环境：uv

**统一使用 uv 管理 Python 版本、虚拟环境、依赖和锁文件。** 不混用 Conda、Poetry 或手工 pip 安装。

## Windows PowerShell 初始化

```powershell
git clone https://github.com/yunfei00/qrft.git
cd qrft
uv python install 3.12
uv sync --all-extras --group dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

首次安装 uv：https://docs.astral.sh/uv/getting-started/installation/

## 增加依赖

```powershell
uv add 包名
uv add --optional decoder 包名
uv add --group dev 包名
uv lock
uv sync --locked --all-extras --group dev
```

`pyproject.toml` 是依赖声明，`uv.lock` 是 uv 生成的锁文件，必须提交 GitHub。不得手写锁文件。CI 使用 `uv sync --locked` 确保依赖一致。

本地环境已生成锁文件，日常执行 `uv sync --locked --python 3.12 --all-extras --group dev`。
若本机旧 pytest 临时目录 ACL 拒绝访问，可设置 `$env:PYTEST_DEBUG_TEMPROOT = "$PWD/temp"` 后执行原测试命令；temp 已被 Git 忽略。
若本机代理下载极慢，可仅在当前 PowerShell 设置 `$env:NO_PROXY = '*'` 后重试 uv；不修改全局网络配置。

## 项目状态

当前是工程骨架和协议原型，不代表编码器、视频解码器或 EXE 已完成。实际验证以 CI 和 `docs/STATUS.md` 为准。

需要用户操作时，只参考 [用户操作手册](USER_ACTIONS.md)。
