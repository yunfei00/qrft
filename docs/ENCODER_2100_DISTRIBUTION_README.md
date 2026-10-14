# QRFT2100 独立命令行编码器 v0.1.0 — Windows x64

适用于 Windows 11 x64；Windows 10 x64 未作本机原生窗口验收。不需要安装 Python 或 uv。

1. 完整解压 `QRFT-Encoder2100-Windows-x64-v0.1.0.zip`。
2. 进入解压所得 `QRFT-Encoder2100` 目录，在此打开 PowerShell。
3. **不要只复制 EXE！必须保留整个目录，包括 `_internal`。**

```powershell
.\QRFT-Encoder2100.exe play "D:\Data\file-or-folder"
```

启动时静默等待口令：手动输入 `qsnfj` 后按 Enter，输入字符不可见。大小写敏感、最多三次；没有 -h/--help，不允许管道输入。它只是本地操作入口检查，不是安全授权/防逆向机制。GUI 不属于本产品。

## 使用命令

先将以下实际路径替换成你的路径，输出须选择尚不存在且在源文件夹之外的目录：

```powershell
.\QRFT-Encoder2100.exe info "D:\Data\example.bin"
.\QRFT-Encoder2100.exe play "D:\Data\example.bin"
.\QRFT-Encoder2100.exe info "D:\Data\ExampleFolder"
.\QRFT-Encoder2100.exe play "D:\Data\ExampleFolder"
.\QRFT-Encoder2100.exe export "D:\Data\ExampleFolder" --output "D:\Output\QR"
```

目录自动在 RAM 生成 ZIP，不写任何磁盘临时 ZIP，不修改源目录。包含隐藏文件、空目录、中文名称；拒绝链接/Junction。默认打包预算 128 MiB（不是整个进程树 RSS 上限），可显式 `--max-archive-mib 256`；超限报错，不自动转存磁盘。打包时请保持源目录静止。

Folder Content MD5/SHA256 是忽略时间、根目录名称和绝对父路径的稳定逻辑摘要。Archive ZIP MD5/SHA256 校验实际传输字节，START 中使用 ZIP MD5；ZIP comment 保存逻辑摘要。压缩库/版本变化可能改变 ZIP，**不能只凭 Folder MD5 混合补传**。

目录补传需从原始 `info` 保存实际 Archive ZIP MD5；missing.txt 每行十进制 DATA 编号或编号范围，例如 `00000000`、`2-4`。每次命令仍需手动输入口令：

```powershell
$originalArchiveMd5 = Read-Host '粘贴原任务 Archive ZIP MD5（32位HEX）'
.\QRFT-Encoder2100.exe play "D:\Data\ExampleFolder" --missing "D:\Data\missing.txt" --expected-archive-md5 $originalArchiveMd5
```

ZIP MD5 不匹配或目录补传未提供原摘要时拒绝发送。完整参数见 USER_GUIDE.md 的参数表；其中源码命令供开发者使用，下载用户直接以 ` .\QRFT-Encoder2100.exe ` 替代 `uv run --no-sync python -m qrft.encoder2100.cli`。

## 播放与录屏

默认固定窗口，完整白色二维码区域 925×925，不缩放/裁切，提示不盖住二维码。首帧 START 静止等待 **Space**；Space 开始/暂停/恢复，**Esc** 退出；START 一次、每个 DATA 一次、FINISH 一次，完成后 FINISH 保留直到 Esc。默认间隔 50ms 是调度目标，生成与系统调度可能延长实际间隔，不跳包。默认最多 3 个生成进程，英文进度约每 5 秒刷新，无默认播放日志。

Windows 11 截图工具录屏必须包含完整白色区域与静区；先保存录屏，再 Esc。提前退出可能返回 130，这与录屏文件是否保存是不同问题。真实截图工具录屏识别率/不同显示器仍未验收，合成 MP4 与桌面预览不能代替真实录屏。

## 协议、校验和故障处理

QRFT2100：2100 字节 DATA、大写 HEX、固定 QR Version40-L。**不兼容旧 v2 1400 字节解码器**，本产品不包含正式 QRFT2100 解码器、Control、Worker 或 GUI。MD5 仅用于完整性校验，不是安全认证。

下载时将 ZIP.sha256 与 `Get-FileHash .\QRFT-Encoder2100-Windows-x64-v0.1.0.zip -Algorithm SHA256` 比对；内部 SHA256SUMS.txt 不包含自身，列出每个发行文件。VERSION.txt 记录版本、源 Commit 与构建运行库信息。依赖许可信息随 `_internal` 保留。

命令无输出通常是在等待隐藏输入。缺少 DLL 请重新完整解压，不能只复制 EXE。显示空间不足时不强制缩放二维码；内存超限请减小目录或明确提高预算；输出已存在时换一个新路径。不要关闭安全软件或绕过系统安全提示。
