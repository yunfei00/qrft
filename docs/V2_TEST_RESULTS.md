# QRFT v2 软件验收记录（2026-10-12）

本轮仅开发分支 `feature/qrft-v2-hex-md5`、软件0.4.0.dev0；不合并main、不发布Release。原里程碑7/10。Draft PR：[#7](https://github.com/yunfei00/qrft/pull/7)。

## 提交与质量门禁

- `af3910aa76902ffd58c25c2d04366342cd61763d`：协议/编码/播放器、Control/Worker兼容、持久恢复、实际EXE验收、中文手册。168项测试通过。
- `ae10b71af6981dcfddc0eb2f583ecf68882f7c30`：真实30fps重采样复现并修复请求20fps却只扫描15fps的漏帧问题，向下取整步幅，不改变协议。**170项测试通过**、无跳过，1条既有Starlette弃用警告。
- 每次提交前均执行 `uv run --no-sync ruff format --check .`、`uv run --no-sync ruff check .`、`uv run --no-sync pytest -q`；全部通过。
- ae10b71的七项CI全绿：Python [38199651842](https://github.com/yunfei00/qrft/actions/runs/38199651842)，四个独立构建38199651807/38199651810/38199651832/38199651864，四程序实际交付[38199651814](https://github.com/yunfei00/qrft/actions/runs/38199651814)，五程序实际验收[38199651862](https://github.com/yunfei00/qrft/actions/runs/38199651862)。后续仅中文记录提交仍再次执行全部门禁。

## 实际测试范围

| 范围 | 结果 | 证据与限制 |
|---|---|---|
| v2字段 | 严格逆向16/32/正文解析、UTF8逗号文件名、MD5、非法HEX/ID、控制重复通过 | protocol_v2测试；v1CRC线格式保留 |
| 1400字节随机QR | 三个确定种子及实际随机块均精确解码 | version33、原图1570px、50%后785px、自动Alphanumeric/数字模式，L/10/4、fit=True；不固定版本 |
| START容量超限 | 明确抛出capacity错误 | 4000个中文字符的内存元数据测试，不截断、不降块；不是Windows合法文件名长度测试 |
| 20fps合成MJPG AVI | START20、DATA各一次、FINISH20逐帧识别；空/全字节/1400/末块恢复MD5一致 | 不是实际录屏MP4 |
| 漏帧/补传 | 真实视频将DATA1替换空白，缺包TXT=1，实际选择性补传后持久任务恢复 | 两次导入共享SQLite；控制帧/乱序/版本锁/冲突/最终MD5均验证 |
| 分布式 | 无START时间片先到、真实HTTP和两个独立Worker进程通过 | 本地进程，不是双Windows/SMB |
| Qt GUI | v2固定参数、实际PNG、20/1/20事件序列、关闭释放通过 | 自动GUI为offscreen；中文原生交互录屏待验 |
| 原生Windows播放器 | 实际CLI EXE OpenCV和Qt显示1400字节块并退出，退出码0 | 本机1920×1080，3.360/3.334秒含启动/生成/调度，不能据此宣称20fps传输 |
| 冻结EXE | 五程序构建，v1完整链路、默认8项、v2环境+链路、独立合成解码项目均通过 | 干净中文目录、清空Python环境、仅系统PATH；全新无Python物理机仍待验 |

本地开发构建保存在 `temp/v2-build/dist`，COMMIT明确标为基线+dirty，而不是最终提交。`temp/v2-build/frozen-evidence-retry` 保存中文HTML/JSON/CSV、进程日志、SQLite和API快照。该v2原始/恢复MD5为 `E3F26EE6ED0FF5BB48711D3833500363`，SHA256为 `0bad25c235308f92490c31bbb57c8b892b46afdac46aaddc8154643982e6d452`，2805字节；缺包1后两个实际Worker和实际CLI补传最终一致。每次随机测试哈希不同，以各次报告为准。

一次本地冻结验收在清单生成完成前启动，环境检查失败、后续项目BLOCKED；已排除流程并按顺序重跑，1109个本地构建文件通过清单验证。失败证据保留，不能计为通过。CI在顺序步骤中构建/生成清单后才运行验收，结果全部通过。

CI构件为 `QRFT-Windows-five-applications` 和 `QRFT-Acceptance-evidence`，不是正式Release。PR工作流COMMIT.txt可能是GitHub为测试自动生成的合并树SHA，不代表已合并main；分支软件来源以上述提交和工作流head_sha为准。

## 人工未验收

Windows11真实截图工具MP4、不同DPI/录制帧率下的识别率、实际50ms显示节奏/长时间稳定性、真实大视频、真实双Windows/SMB、物理网络中断与重连、全新无Python实机。MD5只用于一致性，不是恶意篡改认证。按照 [UA-009](USER_ACTIONS.md) 与 [12步录屏手册](V2_USER_GUIDE.md) 保存系统、构建、录制参数、缺包和原始/恢复MD5证据后再验收。
