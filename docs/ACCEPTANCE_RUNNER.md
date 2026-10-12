# Windows 中文一键验收手册

## v2 开发分支补充（2026-10-12）

本分支0.4.0.dev0新增可选“v2 HEX + MD5 完整链路”。保持默认八项v1不变，先勾选环境检查，再勾选v2；实际CLI导出1400字节/50%二维码，20fps合成AVI，实际Decoder恢复，两个真实Worker EXE领取不同短时间片，可控缺包后实际CLI补传，再恢复并核对MD5/SHA256。报告范围明确为合成视频，不代表真实录屏/双机。缺少新EXE或仍选旧0.3构建会失败，不能冒充v2通过。无Python时可运行 `QRFT-Acceptance.exe --headless --items environment v2`。

本轮170项自动测试与七项CI通过，实际EXE证据及限制见 [V2_TEST_RESULTS.md](V2_TEST_RESULTS.md)。新协议及兼容见 [PROTOCOL.md](PROTOCOL.md)，真实Windows11录屏12步见 [V2_USER_GUIDE.md](V2_USER_GUIDE.md)。本轮不合并main、不发布Release。


第五个独立程序 `QRFT-Acceptance/QRFT-Acceptance.exe` 与原四程序职责分离。请解压完整绿色版，保留所有 `_internal` 运行库及根目录 SHA256SUMS.txt、VERSION.txt、COMMIT.txt。目标电脑无需安装 Python。

## 单机操作

1. 打开验收程序，选择“单机自动验收”，完整程序目录选择包含五个程序子目录的 Release 根目录。
2. 选择报告保存目录。每次运行创建独占 `qrft-acceptance-随机标识` 子目录，不覆盖用户文件。默认选择环境、编码、解码、控制中心、单机链路、双 Worker、网络故障和补传。
3. 点击“开始验收”。后台线程操作真实 EXE；界面显示运行状态和日志。点击“取消测试”会停止本工具创建的进程，保留已完成的证据及报告。关闭窗口同样先取消并等待保存。
4. 结束后打开显示的 `report.html`。同目录含 JSON、CSV、原始随机文件、PNG、AVI、SQLite、恢复文件、缺包列表、API 快照、每个进程的日志。点击“导出报告”会复制到新建目录；不会覆盖同名文件。

本地两个 Worker 是两个独立 EXE 进程，不是两台电脑。合成 MJPG AVI 来自实际 CLI 导出的二维码，包含全部字节值和中文文件名。缺包测试删除一个 DATA 二维码，下载三种缺包列表，再以实际 CLI 的 `--retransmit missing.txt` 生成补传视频并继续恢复。网络故障使用本地 HTTP 代理返回两次 503；实际终止 Worker，等待短租约过期，启动替代进程并验证 SHA256。它不代表真实物理网络断线验收。

## 三种 SMB 角色

- 控制机选择“SMB 控制机 + Worker A”，填写可写 UNC 共享目录，例如 `\\PC-A\qrft-test`，输入仅用于本次验收的 Token。工具在共享下创建独占子目录和测试视频，启动端口 8788 的实际控制中心，日志给出完整 UNC 视频路径。共享应仅向验收机器开放，工具不保存 SMB 凭据。
- Worker B 在另一台 Windows 打开同一版本验收器，选择“SMB Worker B”，填写 `http://控制机IP:8788`、日志提供的完整 UNC 视频路径和相同 Token。共享访问通过 Windows 已有登录会话完成；两端界面无须手工编辑 JSON。
- 两端验证视频直接可读，并登记 Windows MachineGuid 的 SHA256 散列（不记录原始标识）。控制机等待两个不同主机的登记，再注册视频；双方实际 Decoder 各领取一个时间片。控制机保存节点、时间片、原始/恢复 SHA256 和每次租约的包数、重复/冲突数及开始/完成时间。主机身份是客户端声明，不是硬件远程证明。

等待远程登记最长 10 分钟，扫描完成等待最长 5 分钟，均可取消。单机或不可访问 UNC 时显示“不具备条件 / 真实双机 SMB：未验收”。基础双机恢复即使成功，完整 SMB 项目仍为 BLOCKED：还需要按 UA-008 人工断网、重连及录屏验收。本工具不会把部分证据计为完整通过。

控制机向局域网监听仅在明确选择 SMB 控制机角色时启用，API 始终要求 Token。端口已占用会显示启动失败；请关闭冲突的验收实例。不同机器的 Token 只进入内存、HTTP 请求头和 Worker 环境，不写入报告、配置或日志。

独占验收中心带随机实例标识。验收器与其 Worker 请求附带实例标识，错误端口或其他中心即使使用相同 Token 也拒绝这些请求；普通客户端不带该标识时保持原 API 兼容。节点证据中的 frames 指批量提交 DATA/FINISH 帧数（含重复），不含 START 元数据请求，不能当作 ZXing 全部解码帧数。

## 性能和长时间播放

大文件项可选择 10 MB、100 MB、1 GB 或自定义 MB（1–10240）。以最多 1 MB 的随机块流式写入独占测试文件，再测 SHA256。重复随机块用于控制生成成本，不宣称独立随机熵；文件大小真实。**这是哈希性能，不是二维码传输速度，也不是完整大文件二维码验收。** 空间不足会失败并说明原因。

GUI 稳定性可选择 10、30、60 分钟：实际 Encoder GUI 连续播放测试二维码并循环，保存已显示帧数、完成轮次、Qt 平台、实际时长和错误。提前退出、零帧或编码失败不能通过。采样验收器和自有 EXE 的 CPU 时间、200ms 采样内存峰值及进程 I/O；短暂峰值可能漏采，进程 CPU 单核口径可超过 100%。显示窗口播放不代表录屏传输质量，offscreen 结果也不代替桌面人工交互验收。

链路报告的有效包/字节速率以最终唯一数据包和整条测试耗时计算，限于合成 AVI 与 HTTP 本机恢复，不称作纯 ZXing 速度。真正大视频解码与屏幕录制吞吐仍需现场验收。

另有“合成 AVI 解码性能”项目：用实际 CLI 导出的二维码生成小规模视频，真实调用 ZXing 核心，统计合法二维码帧数、采样数、未识别比例和帧/秒，保存为独立指标，不能代替所选 1GB 文件的完整传输。当前实测见 [验收证据](ACCEPTANCE_RESULTS.md)。

维护者可在 Release 根目录用 PowerShell 重复测试，无需安装 Python：

```powershell
$test = Start-Process -FilePath .\QRFT-Acceptance\QRFT-Acceptance.exe -ArgumentList @('--headless','--items','performance','--size-mb','1024') -WindowStyle Hidden -PassThru -Wait
$test.ExitCode
```

默认报告在用户目录的“QRFT验收报告”下新建随机子目录。`--items qr_performance` 测合成解码；`--items stability --stability-seconds 600` 测 GUI。退出码 0 表示所选项通过，1 表示失败，2 表示所选项跳过/条件不具备。仅做性能测试时软件候选版门禁仍为“未满足”。不带 `--items` 的 `--headless` 执行全部默认软件项目。中文日志兼容 UTF-8 与 Windows ANSI。先前报告不影响新一轮验收。

## 报告与故障排查

报告含版本、构建 Commit、机器信息、UTC 时间、项目状态、失败原因、指标、SHA256、日志/证据位置、尚未验收项目，以及软件候选版门禁。SKIPPED/BLOCKED 不计为通过。软件门禁要求环境、编码、解码、控制中心、单机、双 Worker、故障恢复、补传全部通过，且无失败；硬件验收字段不会自动置为通过。

缺少 EXE 或运行库：重新解压完整 Release，不能仅复制 `.exe`。校验失败：重新下载并核对 ZIP SHA256。恢复失败：查看 `task-*.json`、`retransmit-*.json` 与 Decoder 日志。网络测试失败：查看 `fault-*.json` 与进程日志，不关闭 Token 鉴权。结果目录保留供追溯；用户确认不再需要后可自行删除整个对应随机子目录，不应删除其他文件。共享目录的独占测试视频同样保留。

CI 使用 `scripts/acceptance_smoke.py` 复制完整构建到干净中文目录，清除 Python 环境并将 PATH 限于 Windows 系统目录，执行实际验收器 EXE 的 Qt 启动与无界面最小全链路。报告与日志作为独立 CI 构件上传。它不能证明干净目标机的所有安全软件/驱动兼容性。
