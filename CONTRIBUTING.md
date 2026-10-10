# QRFT 开发与协作规范

**GitHub 是唯一事实来源，中文文档为默认标准。** 不依赖聊天记录交接开发。

1. 每次实现提交都要同步测试、`docs/STATUS.md` 和 `CHANGELOG.md`。
2. 没有可复现的测试或运行证据，不能宣称功能完成。
3. 保持四个交付程序和一套共享核心，不复制编码协议实现。
4. Python 环境及依赖统一使用 uv；提交 uv 生成的锁文件。
5. 优先使用 Windows CI 自动验证。
6. 不提交密码、令牌、业务录屏、敏感数据或真实生产配置。
7. 任何需要用户操作的步骤，**必须先提交到 [docs/USER_ACTIONS.md](docs/USER_ACTIONS.md)**，包含 PowerShell 可复制命令、前置条件、预期结果和状态；聊天只需引用操作编号。
8. 新接手人员依次阅读 README、STATUS、ROADMAP、ARCHITECTURE、PROTOCOL、USER_ACTIONS。
