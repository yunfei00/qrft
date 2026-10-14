# QRFT2100 P1 独立编码器自动验收

## 当前更新：文件夹 RAM ZIP、双摘要与单次控制帧

最新功能、稳定序列规范、实际 MD5/SHA256、字节重现和内存报告见 [文件夹测试说明](ENCODER_2100_FOLDER_TESTS.md) 与 [机器可读指标](ENCODER_2100_FOLDER_METRICS.json)。普通文件逻辑保留；目录自动 RAM ZIP、默认打包预算 128 MiB；目录补传强制原 Archive ZIP MD5；START/FINISH 当前各一次，总帧为 N+2，PNG 结构不变。首帧等待和 FINISH 保留已通过原生窗口自动验证。

2026-10-15 本地最终回归：**305 passed / 0 failed / 0 skipped，276.80 秒**；Ruff 格式与静态检查通过。普通文件另跑 100/100 满载 PNG、7/7 合成 MP4；目录样本 5/5 PNG、5/5 合成 MP4，经独立 ZXing 识别、按编号还原 ZIP、内存解压逐项检查通过。START/FINISH 均为一次，目录补传 DATA 与原始编码完全一致，磁盘临时 ZIP 为零。

40 MiB 原始目录流式打包为 8424174 字节 ZIP；独立进程打包耗时 0.694 秒，RSS 峰值 35782656 字节（约 34.13 MiB），不是二维码传输吞吐率。默认预算是 128 MiB 的打包预算，并非整个播放器进程树 RSS 硬上限。实际内存上限失败、源文件变化、真实 Junction/循环目录拒绝均验证；本机无创建文件 symlink 权限，拒绝逻辑由故障注入测试覆盖，不冒称真实 symlink 创建通过。原生截图见 [首帧等待](assets/encoder2100-folder/ready.jpg)、[FINISH 保留](assets/encoder2100-folder/finished.jpg)。新版本真实截图工具录屏尚未实测。

下方为此前版本历史验收，20 次控制帧、45/140/42 帧及性能数字仅属于当时版本，不能作为当前重复次数或本轮新测试结果；旧指标 JSON 保留，不篡改历史证据。本轮全量回归和 CI 结果见上述最新记录与对应分支 Actions。

## 历史基线：独立编码器首次交付

日期：2026-10-14（Asia/Shanghai）。Windows 11 10.0.26200、Python 3.12.13、uv 源码运行。
基线：最新 origin/main `d6770e4`，独立分支 `feature/encoder-cli-2100`。远端旧 PR #7 在本轮开始时已经 Merged，本轮未修改其分支、状态或评论。
本轮不修改旧 Decoder、Control、Worker、GUI 业务实现，不合并、Tag、Release 或构建 EXE。

## 协议、容量与真实识别

- 新协议为 `QRFT2100`，START 内容严格为 `文件名,整体MD5,总包数,QRFT2100`，UTF-8 名称原始大小写保留、从右分割。
- DATA 固定 2100 字节；满载 4248 大写 HEX 字符；尾包不填充，空文件无 DATA。
- QR Version 40-L、单一 Alphanumeric 段、fit=False，177 核心模块 + 两边各 4 静区模块，5 像素整数渲染为 925×925。
- 实测容量边界 4296 字符成功、4297 溢出明确拒绝；不降低分块、不截断 START。
- 1/100/1400/2099/2100 字节 × 全零/全 FF/00～FF 循环/随机内容的真实 PNG 均独立 ZXing 读取、逐字节还原、MD5 一致。
- 2101 字节分为 2100+1；中文逗号混合大小写文件名、无扩展名、空文件、多包、范围与缺包去重均验证。
- 额外 100 个随机满载 PNG：**100/100** 识别成功；真实生成的合成 MP4 **45/45 帧**识别成功（START 20 + DATA 5 + FINISH 20），恢复逐字节一致。
- 合成视频源/恢复 MD5：`9154C07CA414A250901DB71EA385C333`（8411 字节）。不是 Windows 截图工具录屏，也不是旧解码器的兼容性声明。

## 已发现并修复的问题

首次完整测试为 3 失败、44 通过：qrcode 的全零 Reed–Solomon 数据块触发 `ValueError: glog(0)`，发生于 1400/2099/2100 字节样本。
新增本包专用、零系数安全的 GF(256) 迭代除法生成 codewords，继续由 qrcode 完成标准 QR 布局、掩膜和黑白渲染；没有 monkey-patch 库全局函数。
正常随机内容 codewords 与 qrcode 原参考输出逐字节一致，全零修复后经独立 ZXing 验证，未改变任何线上数据。

原生按键验收发现极短 Space 按键可能在 GetAsyncKeyState 轮询前松开；现在同时处理 waitKey 的短按事件和物理按下沿，长按不重复切换。修复前失败日志保留。

CI 接入复跑中有一次 **272 passed / 2 failed**：旧双 Worker 补传等待 40 秒超时，旧纯编码进程报 `OpenBLAS error: Memory allocation still failed after 10 retries`。失败日志与工作区保留在 `temp/encoder2100-ci-fix-regression*`；旧双 Worker 测试不改代码单独复测 1 passed（6.64 秒）。为避免多进程回归时 BLAS 线程池过度分配，源码 CI/开发者测试命令增加仅对测试子进程生效的 OPENBLAS_NUM_THREADS=1、OMP_NUM_THREADS=1，不更改独立 Worker 数、用户全局环境、任何断言或旧业务代码。随后完整复测 **274 passed / 0 failed / 0 skipped，221.01 秒**，日志 `temp/encoder2100-bounded-regression.log`，不隐瞒中间失败。

## 原生播放器与 CLI

- 真实交互式 ConPTY 中完成 CLI 隐藏输入、正确口令、大小写错误、三次拒绝、帮助/未知参数拒绝；非交互管道拒绝，不执行写入。
- 鉴权前静默/解析顺序有自动回归；鉴权后 PNG 导出进程模块审计不包含 PySide6、cv2 或任何旧解码/Control/Worker/GUI 业务模块。
- 另建仅 `--no-dev --extra encoder` 的 Python 3.12 环境，实际交互 CLI PNG 导出成功，PySide6 未安装，导出后进程模块隔离断言通过。
- Computer Use 对真实 Windows OpenCV 窗口实际完成：首帧等待、Space 开始/暂停/恢复、结束保留 FINISH、Esc 退出。暂停期间帧号保持不变。
- 普通源核心测试 140 帧完整；另一次从实际独立 CLI 启动的 140 帧完整；显式全屏选择性补传 42 帧（原始 DATA 1、99）完整。没有跳包，完整结束返回 0。
- Esc 提前结束、关闭窗口和 KeyboardInterrupt 的自动回归检查退出及自有预生成资源释放；不关闭用户其他窗口。
- 普通/补传固定矩形布局、尺寸、静区和无文字覆盖有逐像素断言；实拍截图显示二维码及留白完整。

## 性能实测与限制

测量包含 PNG 真实序列化，不包含识别耗时；连续 100 次计时各自独立，未预缓存 DATA。运行中存在其他本机活动，不保证空载复现一致。

| 指标 | 实测 |
|---|---:|
| 首个 2100 字节 PNG 生成 | 254.763 ms |
| 100 个满载 PNG 生成合计 | 25.297 s |
| 单张生成中位数 | 257.047 ms |
| PNG 大小 | 18620～19162 bytes |
| PNG 测试进程 RSS 峰值 | 62574592 bytes（59.68 MiB） |
| PNG CPU 平均 / 峰值 | 96.48% / 208.3% |
| 1 GiB 流式哈希与全部分块编码 | 20.817 s，其中文件哈希 1.984 s |
| 1 GiB 源码流式进程 RSS 峰值 | 28078080 bytes（26.78 MiB） |
| 实际 CLI 播放进程树 RSS 峰值 | 203812864 bytes（194.37 MiB） |

1 GiB 样本为零初始化文件，实际读取/编码全部字节；**没有生成 1 GiB 的全部 QR，也不代表二维码传输速度**。读取缓冲 1 MiB，分块 2100，播放器最多缓存指定数量 future、两个工作进程，不随文件大小累计全部图片。

50 ms 配置下真实普通 CLI 播放：140/140 帧，间隔最小 **57.228 ms**、中位 **70.557 ms**、P95 **170.989 ms**、最大 **293.909 ms**，标准差 **46.990 ms**，BUFFERING 59 次。
单独开始/暂停/恢复测试剔除实际暂停间隔后，中位 85.194 ms、P95 150.162 ms；暂停本身保留在原始日志，不隐藏等待。
全屏补传中位 67.533 ms、P95 90.972 ms。**本机未达到恒定 50 ms/20 FPS**；配置为最短驻留，生成与窗口调度增加延迟时保持前帧、明确记录等待、不静默跳包。
日志时间是 imshow 提交时刻，不是显示器光学刷新测量；CPU 为采样进程占用，可大于 100%，不是整机百分比。

## 可靠性、自动化与证据

权限测试在本轮新建目录上设置当前 SID 写拒绝，再经真实 CLI 验证返回 2、没有输出，finally 恢复该测试目录 ACL；不调整用户目录或系统设置。
磁盘不足用故障注入模拟 OS 余量为零，未填满磁盘；权限异常另有故障注入回归。不存在/错误路径、已存在输出拒绝、已有用户文件保留、导出取消保留日志且不产出完整清单、编码期间源文件改变、重复编码一致均覆盖。

最终本地全量回归 **274 passed / 0 failed / 0 skipped**，221.01 秒（早一轮 226.06 秒亦全通过）；其中独立编码器 **53 项**（单独执行 73.77 秒），另有既有 Starlette/httpx 弃用警告 1 条。Ruff 格式检查（129 个文件）、静态检查、git diff --check 均通过，没有删除或跳过既有测试。
Commit 可在 [本开发分支](https://github.com/yunfei00/qrft/tree/feature/encoder-cli-2100) 查看；推送后的精确提交 CI 结果见 [Windows Python CI](https://github.com/yunfei00/qrft/actions/workflows/ci.yml?query=branch%3Afeature%2Fencoder-cli-2100)，本地实测与 CI 机器性能分别报告，不将两台机器的数字混用。
可复现命令见 [使用手册](ENCODER_2100_USER_GUIDE.md) 第 6 节；使用已有 `ci.yml`，在现有全量源码回归之外新增 QRFT2100 实际 PNG/MP4/流式验收及证据上传，不打包。新文件工作流在默认分支尚未注册时不能 workflow_dispatch，因此不依赖新工作流或提前合并 main。
旧 PR 的 EXE 工作流不适用于本轮，所以提交使用 `[skip ci]`，随后显式 dispatch 源码验收工作流；源码门禁仍必须完整通过。

机器可读指标：[ENCODER_2100_METRICS.json](ENCODER_2100_METRICS.json)，包含源码 SHA256、识别结果和实际帧间隔。
原生窗口截图：[READY](assets/encoder2100/ready.jpg)、[PAUSED](assets/encoder2100/paused.jpg)、[全屏补传完成](assets/encoder2100/fullscreen-retransmission.jpg)。这些是桌面工具生成的缩放预览，不用作原始 925×925 PNG 识别率输入。
本地完整证据：

- `temp/encoder2100-p1-final/`：100 PNG、合成 MP4、随机源文件、补传 PNG、1 GiB 流式样本、report.json。
- `temp/encoder2100-p1-fixed/`：修复后的协议/视频证据、原生暂停日志和截图；`native-key-before-fix.jsonl` 保留短按失败现场。
- `temp/encoder2100-p1-native-cli/`：实际 CLI 日志、READY/FINISHED 截图、140 帧显示日志、进程树资源指标。
- `temp/encoder2100-p1-retry-fullscreen/`：真实 CLI 全屏补传、42 帧显示日志及截图。
- 初次失败测试目录、短按失败日志和全量回归日志保留，不自动删除用户文件或历史验收数据。

## 尚待物理设备验证

真实 Windows 截图工具录屏识别率、不同 DPI/显示器/相机以及连续长时录制仍未测，不能把 PNG/合成 MP4 成功扩展为这些项目通过。
本阶段不实现正式解码器或旧协议兼容改造；后续独立解码器必须显式识别 QRFT2100 的 START，不能用 DATA 猜测文件归属。
