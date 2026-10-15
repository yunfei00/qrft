# QRFT2100 P1 独立编码协议

本协议独立于旧 v1/v2，不声称旧解码器兼容；encoder2100-v0.1.0 发行只包含独立命令行编码器。后续新增的 [单机项目源码入口](SINGLE_DECODER_USER_GUIDE.md) 已显式支持此 QRFT2100 标记，不修改这里冻结的线格式；旧 GUI/Control/Worker 不因此自动支持 QRFT2100。
所有帧在线上均为 `CONTENT_HEX + CONTENT_MD5_HEX + PACKET_ID_HEX`，只允许 `0-9A-F`，无分隔符。
CONTENT_HEX 是原始内容的大写 HEX；紧随其后是原始内容 MD5 的 32 位大写 HEX；最后是八位十进制 ASCII 包号的大写 HEX（16 字符）。MD5 是完整性检查，不是安全认证。

## START

包号 `88888888`。内容是 UTF-8 文本 `文件名,文件MD5,总包数,QRFT2100`。
文件名使用 basename，保留原始大小写及 UTF-8 字节，可含逗号；解析时从右分割最后三个逗号。
文件 MD5 为整个原文件的 32 位大写 HEX；总包数为规范十进制非负整数（空文件为 `0`）。
例如 `MiX,中文.bin,D41D8CD98F00B204E9800998ECF8427E,0,QRFT2100`。
START 只发送一次，首先静止显示直到用户按 Space；开始后至少驻留指定间隔再进入 DATA。固定 Version 40-L 无法容纳的名称必须报错，禁止截断。

## DATA

文件按固定 2100 字节分块，末包保留实际字节数，不填充；编号从 `00000000` 递增。
有效编号为 0～88888887，最多 88888888 包；88888888 及以上不分配给 DATA。
空文件没有 DATA。每个 DATA 默认一次。满载帧严格为 4200+32+16=4248 字符。
`00000000` 的编号 HEX 为 `3030303030303030`。

## FINISH

包号 `99999999`，原始内容严格为小写 UTF-8 `finish`，内容 HEX 为 `66696E697368`。
FINISH 只发送一次，驻留后显示 FINISHED，保留同一二维码直到 Esc；仅表示发送结束，不表示接收成功。

## 二维码与显示

固定 Version 40、L、强制 Alphanumeric（不使用自动 byte 模式）、box_size=5、border=4；fit=False。
177×177 核心模块，加四边 4 模块静区共 185×185，输出 925×925 黑白像素，无插值。
40-L 字母数字理论容量为 4296 字符；4248 字符满载余量 48。
像素坐标 (10,35) 起为固定 925×925 白色录屏区，窗口 945×1010；状态和控制提示在区外。
不足显示空间时明确报错，不缩小二维码、不裁切。可显式全屏，仍保持整数像素原尺寸。
START/DATA/FINISH 默认每帧 50 ms（可用统一 interval-ms 调整）；首帧等待 Space，结束保留最后帧。

## 补传与独立校验

范围或 missing.txt 仅选择原始 DATA 编号，仍发送完整 START、FINISH 各一次；总帧数为所选 DATA 数 + 2。PNG 仍导出两个控制帧各一张，manifest.control_repeats=1。
missing.txt 为每行一个十进制编号（允许八位补零），或一行闭区间 `12-18`，空行及 `#` 注释忽略。
先校验全部编号不越界，再按升序合并区间、去重，文件分块、原编号、内容保持不变。
帧校验从末尾逆向分割 16/32/剩余字符；拒绝非法 HEX、奇数长度、非八位十进制编号及 MD5 不符。
测试校验器只用于本阶段验收，不是正式解码器。不同文件没有 DATA 来源标识，不可自动混合任务。

## 文件夹传输与两种摘要

目录自动转换为内存 ZIP，START 的文件名为 `<根目录名>.zip`，**START 的 MD5 为实际 ZIP 全部字节的 MD5**，DATA 是 ZIP 原始字节按固定 2100 分块。不在线上增加字段。
独立 Folder Content MD5/SHA256 描述逻辑内容，写入 ZIP comment，不替代 ZIP MD5。

逻辑序列规范 `QRFT2100-FOLDER-1`：摘要初始化字节 `QRFT2100-FOLDER-CONTENT\x00\x01`。
包含根目录条目（相对路径空字符串）；随后所有文件和子目录按相对路径 UTF-8 字节升序排列，分隔符统一 `/`，不做大小写折叠或 Unicode 合并。
每个条目：1 字节 ASCII 类型 `D`/`F` + 8 字节大端无符号路径字节长度 + UTF-8 路径 + 8 字节大端无符号内容长度 + 原始内容。
目录内容长度为 0、无内容；文件内容长度为真实字节数。所有目录（含非空目录）、隐藏文件、零字节文件均纳入；没有时间、绝对路径、权限或外层根名称。

ZIP 固定 UTF-8 相对路径顺序，条目时间 `1980-01-01 00:00:00`；create_system=3、create/extract_version=20（需要 ZIP64 时按标准提升）、普通文件 0644/目录 0755、internal_attr=0、条目 comment/extra 为空（必要 ZIP64 extra 除外），所有条目 ZIP_DEFLATED、级别 6。
根目录不作为外层 ZIP 条目；ZIP comment 为 ASCII JSON，键排序、无多余空白，仅含 format、folder_content_md5、folder_content_sha256。
Python/zipfile/zlib 版本可能改变压缩字节，运行版本记录在 info 和导出 manifest，不加入 comment。相同环境重复 ZIP 字节一致不等于承诺跨版本一致。

目录使用 `--missing`、非零 `--start-id` 或显式 `--end-id` 时，必须提供初始任务的 `--expected-archive-md5`；重新打包后 MD5 不同则拒绝，不播放、不导出。逻辑摘要相同不能证明补传 DATA 相同。
目录打包只使用 BytesIO/ZipFile、64 KiB 原文件读取块，无临时 ZIP、磁盘缓存或回退。默认打包内存预算 128 MiB，计入目录清单估算、缓冲余量；预算不等于整个 Python/QR 进程树 RSS 上限。详见 [文件夹验收说明](ENCODER_2100_FOLDER_TESTS.md)。
