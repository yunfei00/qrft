# QRFT2100 Encoder CLI v0.1.0 版本归档

独立编码器功能冻结；Tag 为 `encoder2100-v0.1.0`，Release 标题 `QRFT2100 Encoder CLI v0.1.0 (Windows x64)`。这不是仓库 archived，不合并 main，PR #8 保持 Draft，旧 PR #7 和已有 Releases 不变。

用户下载入口：[GitHub Release](https://github.com/yunfei00/qrft/releases/tag/encoder2100-v0.1.0)。资产为 `QRFT-Encoder2100-Windows-x64-v0.1.0.zip`、同名 `.zip.sha256`；源提交与准确构建版本记录在 ZIP 内 VERSION.txt。Tag 指向通过源码 CI 和冻结验收的发行提交；发布上传已经验收的同一 ZIP，不重新构建替换。

## 发行内容与范围

```text
QRFT-Encoder2100/
  QRFT-Encoder2100.exe
  _internal/                 # 完整 Python/DLL/编码依赖及其许可资源
  THIRD_PARTY_LICENSES/      # Python/qrcode/Pillow/OpenCV/NumPy/PyInstaller 许可文本
  README.md                 # 中文 Windows 发行说明
  USER_GUIDE.md
  VERSION.txt
  SHA256SUMS.txt             # 除自身外所有文件
```

PyInstaller onedir/console，真正入口为 `qrft.encoder2100.entrypoint` → `qrft.encoder2100.cli`；入口先执行 freeze_support，让 Windows spawn 生成进程在口令/参数解析前分流退出。不包含旧 CLI、Decoder、Control、Worker、GUI/Qt 或验收驱动；构建时审计 PYZ 模块，保留必要 NumPy/Pillow/OpenCV 依赖许可证。项目根若有 LICENSE 则一并复制，不捏造项目许可。

文件/目录自动识别、RAM ZIP 双摘要、安全补传、2100 字节、大写 HEX、Version40-L、START/DATA/FINISH=1/N/1、50ms、固定白色区域、Space/Esc 均冻结。默认最多三生成进程，五秒英文进度，无默认播放日志；内存打包预算 128 MiB，不是整个进程树 RSS 上限。MD5 不是安全认证，不兼容旧 1400 字节解码器。使用说明以 [USER_GUIDE 第 8 节](ENCODER_2100_USER_GUIDE.md#8-zip-解压后运行发行用户推荐) 和 [发行 README](ENCODER_2100_DISTRIBUTION_README.md) 为准。

## 构建、测试与可追溯证据

先执行 Ruff、完整 pytest 和已有普通文件/文件夹 PNG/MP4/ZXing 验收。独立工作流为 `.github/workflows/build-encoder2100.yml`（Windows Encoder2100 Release）；分支未合并 main 时通过已注册的 ci.yml 输入 build_encoder2100=true 调用它，在源码门禁成功后构建、从最终 ZIP 解压再运行 EXE 测试，上传同一 ZIP、SHA256、build.json 和 frozen-report.json。

维护者在本分支、干净工作区与 Python 3.12 环境运行（普通发行用户无需运行）：

```powershell
Set-Location 'D:\code_2026\qrft'
uv sync --locked --python 3.12 --all-extras --group dev
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败' }
$build = Join-Path (Get-Location) ('temp\encoder2100-build-' + [guid]::NewGuid().ToString('N'))
$evidence = Join-Path $env:TEMP ('QRFT2100-frozen-' + [guid]::NewGuid().ToString('N'))
uv run --no-sync python scripts/build_encoder2100.py --root "$build"
if ($LASTEXITCODE -ne 0) { throw '打包失败，不得发布' }
uv run --no-sync python scripts/encoder2100_frozen_acceptance.py --zip (Join-Path $build 'QRFT-Encoder2100-Windows-x64-v0.1.0.zip') --root "$evidence"
if ($LASTEXITCODE -ne 0) { throw '冻结 ZIP 验收失败，不得发布' }
uv run --no-sync python scripts/encoder2100_frozen_acceptance.py --root "$evidence" --native
# 此次默认不写播放器日志；在原生窗口验证等待/暂停/继续/结束保留后 Esc。
if ($LASTEXITCODE -ne 0) { throw '冻结播放验收失败，不得发布' }
uv run --no-sync python scripts/encoder2100_frozen_acceptance.py --root "$evidence" --native --source (Join-Path $evidence 'Native Folder 中文 default\binary.bin')
# 同一冻结 EXE 的普通文件播放，仍由 Space 开始、Esc 结束。
if ($LASTEXITCODE -ne 0) { throw '冻结普通文件播放失败，不得发布' }
```

自动验收驱动在源码侧使用真实 ConPTY 手动输入等效测试按键，未将口令放在 EXE 参数/环境/管道中，未修改产品校验。子 EXE PATH 只有 System32，CWD 为系统临时目录下的全新中文解压目录，无源码/venv；校验 Python/uv 不可查找、冻结模块路径及内置 runtime SHA256。开发者 QA 使用 Python 不代表发行用户需要 Python。

`frozen-report.json` 保留准确 ZIP SHA256、构建 Commit、每个命令/退出码、鉴权前静默与隐藏输入、真实加载模块与进程信息、实际 PNG 数和两种摘要。覆盖空目录/空文件、隐藏/中文/空格/长路径、重复打包与时间不变性、ZXing 逐包还原、内存解压及独立逻辑摘要重算、补传一致/错误拒绝、源只读、已有输出保护、4 MiB 超限及无临时 ZIP。原生播放另保存 native-default-report.json（实际三个 worker 的 PID/EXE/命令/退出、英文进度）和可选诊断日志、截图；默认与显式日志分开验收。

发布前从 CI 下载原 ZIP，再在本机全新目录重复真实冻结测试与原生窗口操作；不以源码结果或本地重新构建文件代替远端待发布字节。完整源码日志、CI 验收与 Release 附加 JSON 报告分别记录测试数量；没有执行的测试不计入 PASS。

## 本机预验收与最终发行证据

本机候选构件预验收（2026-10-15）：Ruff 通过；完整回归 **307 passed / 0 failed / 0 skipped，254.47 秒**；源码普通文件 100/100 满载 PNG、7/7 合成 MP4，目录 5/5 PNG、5/5 合成 MP4 通过。首份本地冻结 ZIP 已完成 10 类检查、18 次 EXE 调用、独立 ZXing/内存 ZIP 还原及双摘要验证。原生默认播放与显式诊断播放分别运行，实际三个冻结 worker 正常退出；诊断序列 403 帧（START 1、DATA 401、FINISH 1），暂停保持包号、继续、FINISH 保留与 Esc 通过，终端普通进度间隔约 5 秒。本地候选仅作预验收；最终发行字节及精确提交以成功的 CI 构件、Release 的 SHA256 和附加验收 JSON 为准，不把基线源码 CI 当成冻结发行结果。

发行目录审计补齐实际安装版本的 Python、qrcode、Pillow、OpenCV、NumPy 与 PyInstaller 许可文本后，本地最终完整回归再次 **307 passed / 0 failed / 0 skipped，257.86 秒**，Ruff 通过；包含许可文件的候选 ZIP 10 类/18 次交互式 EXE 检查通过。独立打包预验收 CI run `38604283063` 的源码与冻结 EXE 两个任务均成功；最终发布前仍须对后续最终提交再跑 CI、下载原构件、本机复验，不能发布前一候选 ZIP。

## 尚未验收的物理环境

真实 Windows 截图工具屏幕录制后的 QRFT2100 识别率、不同显示器/DPI/物理设备未验收；合成 MP4、原生窗口截图和调度日志不能代替光学/录屏吞吐率。Windows 10 原生窗口、ARM64、第二台电脑/真实 SMB 不在本次 Windows 11 x64 单独编码器发行验收范围。
