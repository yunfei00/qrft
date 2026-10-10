# QRFT 用户操作手册（唯一操作入口）

**约定：所有需要用户执行的操作，必须先写入本文件，再在聊天中提示“请按照 [用户操作手册](USER_ACTIONS.md) 的 UA-XXX 执行”。** 命令统一使用 Windows PowerShell，确保可复制。每项必须写明执行时机、环境、命令、预期结果和反馈方式。CI 能自动完成的事情不要求用户重复执行。

## UA-001：Windows 本地 uv 环境验证

**状态：待执行；仅在需要本机复现或 CI 失败时执行。当前无需操作。**

环境：已安装 Git 和 uv 的 Windows PowerShell。uv 安装指南：https://docs.astral.sh/uv/getting-started/installation/

```powershell
git clone https://github.com/yunfei00/qrft.git
cd qrft
uv python install 3.12
uv sync --all-extras --group dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

预期：自动建立 `.venv`；测试和静态检查通过。若失败，反馈出错命令及完整输出；成功则反馈 `UA-001 PASS`。

## UA-002：真实二维码录屏验证

**状态：暂不需要。** 编码器完成后，将在这里补充录屏软件设置、示例文件、操作命令、预期哈希及反馈格式。

## UA-003：Windows 局域网 SMB 分布式解码验证

**状态：暂不需要。** 工作节点和控制端完成后，将在这里补充共享权限配置、节点命令、测试数据与预期结果。不得提交真实密码或令牌。

## UA-004：四个 Windows EXE 验收

**状态：暂不需要。** 打包完成后，将在这里补充下载地址、四个程序的启动命令及验收标准。

## 状态维护

执行完成后在 GitHub 记录：执行日期、命令、PASS/FAIL、日志位置。未验证不得标为通过。
