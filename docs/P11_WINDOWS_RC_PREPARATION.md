# QRFT v2-P11：Windows 候选版准备与打包后验收

> **状态：待 Codex 执行。本阶段不合并 main、不打 Tag、不发布 Release。**
> 本文档是 P11-A 的工作范围，不代表已完成；在 P11-A 全部通过并得到用户明确授权后，才可以另行决定 P11-B 合并和 v0.4.0 候选版发布。
> 代码仓库：yunfei00/qrft；分支：feature/qrft-v2-hex-md5；现有 PR #7 保持 Open / Draft。

## 一、可靠基线与发布约束

- v2-P8：编码器 GUI/CLI 与 Windows 真实录屏、缺包补传已由用户报告 PASS。
- v2-P9：新解码 GUI 使用 P8 真实 MP4 完成首段、缺包、保存重开、补传、恢复及 MD5/SHA256，用户报告 UA-011 PASS；Codex 合成 MP4 自动验收独立记录为 27 PASS / 0 FAIL / 1 NOT TESTED。
- v2-P10：64 KiB、1/4/10 MiB 合成 MP4 及 1/2/4 Worker 对比；10/30 分钟重复短片 GUI 稳定性、故障恢复通过；SQLite 100 MiB / 1 GiB 入库/恢复通过；最终 221 项 pytest 通过（无跳过）。详细数据见 P10_STABILITY_PERFORMANCE_RESULTS.md 与 P10_BENCHMARK_SUMMARY.json。
- **不要把 SQLite 的 1 GiB 恢复视为 1 GiB 二维码视频**，也不能把重复短片 30 分钟等同单段长视频。
- 未验收：第二台实体 Windows 的真实 SMB、物理断网恢复、50/100 MiB 或 1 GiB 完整 QR 视频、真实大录像吞吐、60 分钟 GUI。这些不阻止测试版交付，但必须清晰标注“未验收”，不能宣称生产级全范围通过。
- 本次只开发、构建并验证 Windows 候选**构件**，不发布 Release，不更改旧发布、不更新旧 Tag、不把 PR 标 Ready、不合并 main。尊重用户之前的选择：**Windows 11 + Python 3.12 + uv 源码运行仍是优先支持方式**，EXE 只是新增一种可选交付方式。

## 二、先确认旧打包链路的差距

现有仓库同时存在：
- .github/workflows/windows-delivery.yml：只构建四程序；
- .github/workflows/build-acceptance.yml：旧五程序候选版；
- 单独的 build-encoder.yml / build-gui.yml / build-decoder.yml / build-control.yml；
- 新增的 src/qrft/decoder_gui/main.py 在旧五程序流程中尚未成为独立打包程序；
- scripts/windows_smoke.py 和 docs/OPERATIONS.md、旧 README 段落主要针对旧 v1/四程序交付。

P11-A 要对照现有源码/实际 CLI 参数逐一更新这些流程，保持旧构件的职责和命令兼容。不得简单宣称原“五程序 EXE”已覆盖新“解码 GUI”。

## 三、六程序目标（原则上延续现有拆分）

1. QRFT-Encoder-CLI.exe：保留 P8 的隐藏口令交互、参数保护、v1/v2 导出及播放；打包后也不提供未授权的 -h/--help 泄露。
2. QRFT-Encoder-GUI.exe：保留 P8 GUI 文件选择、编码、固定区域播放器与 Space 控制；GUI 无口令。
3. QRFT-Decoder.exe：保留本地解码 CLI 和远程独立 Worker 子命令。
4. QRFT-Control.exe：保留 FastAPI 管理中心与 HTTP/SQLite。
5. QRFT-Acceptance.exe：保留已有独立验收工具；适配新的候选版构件，不能覆盖历史 0.3.0rc1 的交付证据。
6. **新增 QRFT-Decoder-GUI.exe**：P9/P10 已验证的统一单机/分布式中文桌面入口。

对第 6 个工具必须解决冻结环境里的真实子进程问题：源码 ManagedSession 目前使用 Python 的 sys.executable + -m 模块启动本地 Control 与 Worker，在 PyInstaller 窗口 EXE 内不能直接假设存在 Python 解释器。设计明确、可靠、带回归的 frozen/source 双路径：源码时使用现有 Python -m；打包时从完整交付目录找到对应 QRFT-Control.exe、QRFT-Decoder.exe worker，以环境变量内的临时 Token 安全传递、不将 Token 写到命令行或 GitHub。不能递归启动 GUI EXE 或让 UI 显示成功但 Worker 未启动。组件缺失时用中文报清楚错误。关闭时只能清理自己启动的进程，不能结束用户自己启动的其他服务。禁止固定写死工作目录、用户名或端口；允许随机 localhost 端口并管理工作区权限、日志和数据库。

## 四、Windows 打包、原生 GUI 与真正端到端验收

使用 PyInstaller onedir 或经证明等效的方式，打包完整六程序的运行库、Qt 插件、ZXing、OpenCV、uvicorn 等依赖和必要资源。测试必须从与源码仓库分离的新建目录启动，避免因为机器已安装 Python 或设置了 PYTHONPATH 而“假成功”。

必须实际执行：
- 全量 Ruff/pytest（不能删除、跳过现有检查），验证当前源码 HEAD；
- 构建后检查 6 个 EXE 和各自运行库存在；清理构建/临时目录必须只限 P11 专用目录，不得清理用户历史任务；
- 独立测试 Encoder GUI/CLI、Decoder CLI/Worker、Control、Acceptance、Decoder GUI 的启动及关闭；控制台/窗口程序状态正确，无意外弹黑框、Qt 缺失 DLL 或无限重启；
- 打包后的 QRFT-Decoder-GUI.exe 自动创建 localhost Control 和至少一个**实际独立 Worker EXE**，通过 Qt 真实控件导入由 v2 真实编码核心合成的可解码 MP4，首段缺包并导出 TXT/CSV/JSON、补传合并、自动恢复、源文件与恢复文件字节、MD5/SHA256 相同；
- 关闭/重开、取消/暂停/继续、任务持久化、错误视频和跨用户工作区保护；日志保存，已验证文件拒绝覆盖；
- 本机至少 2 个独立 Worker.exe 处理不同逻辑时间片，非模拟对象；结果一致，Node ID 唯一、租约/重试/清理正常；
- 中文/逗号文件名、空文件/短末块、v1/v2 混合拒绝等至少执行代表性 frozen 回归；旧 v1、已验收编码器 v2 行为不退化；
- Python CI 适用项和新增 Windows 打包 smoke 都基于对应代码提交，**不能用源码 CI 替代 EXE 冒烟**；
- 非交互 CI 可以跑用 Qt 驱动的原生窗体/专用自动验收入口；如果不可用，只能标成 NOT TESTED，不能把“生成 EXE 文件”当作功能通过。

## 五、文档、发布清单与版本一致性

- 当前 pyproject.toml 和 src/qrft/__init__.py 都是 0.4.0.dev0；P11-A 不急于升为正式 0.4.0。先保证来源一致，候选版本号和 Release 只能在用户批准后修改。
- 每个产物要携带相同的 Commit、VERSION.txt；Windows 文件名、程序列表、起动命令与真正生成的 EXE 对齐。
- 生成全文件相对路径 SHA256SUMS.txt、打包 ZIP 的 SHA256、构建环境和工作流链接。要**实际从构件重新下载/独立解压**后验证清单，而非只校验构建输出目录。
- 更新 README、docs/OPERATIONS.md、docs/STATUS.md、docs/ACCEPTANCE_RESULTS.md、docs/USER_ACTIONS.md、交付/架构相关文档的旧版本说明；特别修正旧 v1 命令文档与 P8 v2 CLI 口令/无帮助接口的冲突。可保留旧候选版使用方法，但要明确标“历史 v0.3.0rc1，不适用于 v2”。
- 新增 docs/P11_WINDOWS_RC_RESULTS.md 和 docs/P11_RELEASE_DECISION.md，明确逐程序 PASS / FAIL / NOT TESTED、运行环境、测试输入、原始/恢复哈希、EXE SHA256、压缩包 SHA256、CI/构件来源、未测及发布阻塞项目。
- 所有需要用户实际操作的项目先编号写入 docs/USER_ACTIONS.md，自动完成的不要重复要求用户做。
- Token 不写公开配置/日志/网页 URL，哈希清单不包含秘密；未提供的数据必须明确“未获取”。

## 六、执行及决策门槛

1. Codex 一次性执行：同步→检查源码→修复打包/子进程路径→增自动化测试→打包六程序→独立目录真实 EXE 链路→失败修复重跑→质量门禁→文档→提交和推送当前分支。
2. 最终给出真实 Commit、6 EXE 的启动/端到端结果、Windows CI、构件链接、目录结构、ZIP/hash、冻结 GUI 的进程树和完整恢复证据；尽可能直接存于 Actions Artifacts/专用独占验收目录，不要无权限上传用户文件。
3. PR #7 保持 Draft；P11-A 交付后暂停在“可供用户决定的候选构件”，**没有用户新的明确授权不得合并 main、Tag、发布 Release**。
4. 若真正需要第二台物理 Windows 才能验证 SMB/断网，则明确保留 NOT TESTED，说明单机候选版是否可试用，并将分布式生产可用性标为待验证。
5. 任何部分失败必须列具体日志、可复现路径、受影响构件，不得为了赶发布弱化测试或绕过口令。
6. P11-A 完成后由助手与用户共同检查报告，决定 P11-B：是否允许候选版 prerelease（注明双机限制），以及什么时候现场测 SMB 后进一步发布正式版。

### Codex 交付原则

请直接修改、测试、修复、提交、推送；如果可自动完成，不要反复让用户运行脚本。未执行/受环境限制的项目真实标注，不得冒称软件全部硬件验收完成。P8/P9 已完成的人工源码验收不重复。
