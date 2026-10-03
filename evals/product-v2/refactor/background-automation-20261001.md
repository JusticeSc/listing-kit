NOT-AUTHORITY: point-in-time user authorization evidence; authority remains docs/product-v2-refactor-plan.md §3.

# Chrome 后台自动化授权

用户明确授权 Chrome 无头模式后台静默执行本地端到端点击、输入、页面内鼠标/键盘事件（包括 Tab、Enter、Escape）、滚动/拖拽、已有授权测试素材的文件输入、截图、刷新、重开及导入导出内容验证，无需逐项询问。浏览器接口事件不等于系统级键鼠；文件输入和捕获下载不使用 Windows 文件对话框。

禁止 Edge、可见窗口、置顶/抢焦点、桌面鼠标、向前台系统窗口发按键、修改日常浏览器配置。使用独立临时浏览器配置与测试数据，默认本地 fake provider；不付费、不向外部供应商上传、不提交推送、不部署。无头不可达专项记录精确缺口并继续其他可达项；确需窗口或额外权限另行获批。自动化不能替代产品发起人 C17 与首次使用者 C15 的真人理解/视觉/易用性验收。

## 当时的执行证据

- 已关闭此前自行启动的 Edge 与可见测试 Chrome；此后仅使用无头 Chrome，不修改系统重定向/日常配置。
- 新独立配置：`C:\Users\31368\AppData\Local\Temp\amz-r21-chrome-headless-ptlNx0`。`Browser.getVersion` 返回 `Chrome/154.0.8037.93`，UA 包含 `HeadlessChrome/154.0.0.0`。
- 所有页面网络目标限定 `127.0.0.1`；本地正式 product handler 经测试服务器装配 fake semantic/image/review/suite-review。
- 进程 32636 的实测命令行含 `--headless=new --user-data-dir=...amz-r21-chrome-headless-ptlNx0 --remote-debugging-port=15187`，`MainWindowHandle=0`。仅查询自建进程，无桌面输入或前台切换。
- 新配置初始 IDB 为 0 项目/0 文档/0 资产；导入 UI 实际产生的当前格式项目包后为 1 项目/58 文档/6 资产，商品名“白色保温杯”，审核入口可用，工作区错误为空。
- 本条不证明七任务全部通过、不证明最终交互改善、不消除既有启动间歇问题、不证明 Edge/桌面专项或真人走查。
