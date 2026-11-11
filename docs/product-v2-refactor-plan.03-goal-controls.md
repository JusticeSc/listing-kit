<!-- 拆分件 product-v2-refactor-plan.md · 第03/42片 · goal-controls · main 行49–61 · 源 11902b32651f4690f7367624377dcde6652e0a97 -->
> 导航：父页 [product-v2-refactor-plan.md](product-v2-refactor-plan.md) · 02 [上一片](product-v2-refactor-plan.02-goal-outcomes.md) · 04 [下一片](product-v2-refactor-plan.04-goal-binding.md)
> 本片逐字节保存 main 原件「§2.1 Goal：验证、边界与停止条件」，不重写、不摘要；完整计划须按父页目录顺序与注册表规则拼接后阅读。
> 续接标记：本片首行补围栏重开行 ```text，已注册为 remove_prefix，拼接前删除。
```text
## Verification
复用 config/product-v2/verification.json、计划 §17.5 及现有页面 walk/Adapter Transport/发布链，不新增验证平台。按受影响范围执行当前命令：npm run check:types；npm run build:frontend；npm run build:frontend-node；涉及 envelope 时 npm run build:envelope；涉及领域规则时 npm run test:domain 或其现有受影响行为入口。当前没有 check:generated，不运行或伪造旧脚本。每个完整用户纵向实际启动正式页面，以独立 Chrome 无头临时 profile 上传合法素材、填写/确认、点击/键盘、两模式来源、采用、实际下载/导入/刷新，核请求/原 action、IDB 文档和 Blob、ZIP 原字节及截图；测试全绿不代替 smoke。项目传输/返工复用 uv run --locked python tools/verify_v2_6_3_project_transfer.py --label <实际候选标识> 和 uv run --locked python tools/verify_v2_5_4_rework_loop.py --label <实际候选标识>，真实 CLI 先按当前代码核对。最终冻结用 uv run --locked python tools/verify_v2_7_1_regression.py --rounds 2 --stamp <实际候选标识>，不使用 --only 放行。发布用现有受保护 CI/CD、uv run --locked python tools/release_transaction_probe.py --page-smoke --base <既有可信HTTPS-origin> 及实际受测 image 内 --fingerprint --runtime-root <实际代码目录>，再走完整线上数据和同源恢复；空项目 smoke/本机 fingerprint 不代替成品验收。权威/状态用 uv run --locked python tools/check_docs.py --no-run 和 uv run --locked python tools/refactor_resume.py --json；正式状态/依赖改变才核对现有相关反例。真实收费必须在正式 registry/Adapter/产品路径、当前官方价格与素材/凭据准入及逐笔预留成立后，保留原图和全部失败/Unknown；不以旧图、fake、HTTP200、Schema/hash或自评替代消费者与像素证据。

## Boundaries
用户已明确“开始”并授权助手选择尝试上限；允许完整剩余产品交付及必要的 app/、src/、tools/、tests/、config/、构建/发布配置、现有权威文档/状态/费用记录改动，以及相关分支提交/推送、独立审查与实时保护成立后的 PR 合并和既有环境发布。以当前仓库实际目录、既有 owner/接口/技术选型为准，同包迁移所有消费者并删过时活入口，不全仓重写、恢复整包封存WIP或重做已完成基线/PR18。PR18在正式绑定后按当前源头说明补正和真实新差量审查/CI、保护成立才阶段合并，阶段上线不算最终交付。
新增模型额度仅5元，生图最多12次且每次1张，理解/创作辅助/复核合计最多4次，仅已批准现有模型；金额或类别次数先到即停，失败/Unknown/返工/对照均计。沿计划 §17.6 固定授权幂等键，精确承接最新封存完整账且保全工作账新记录，只激活一次；旧累计/失败/预留不清零，不借旧余量或重新激活。激活不发送请求，每次先核当前官方最大费用、精确型号、合法素材/hash及既有安全凭据注入再预留。没有预算内必然合格的承诺。
禁止未经批准的新模型/重大依赖或总体架构替换、账户/云项目库/自主Agent/通用重试调度遥测平台、私有上传或新凭据渠道、不可逆用户数据操作、读取GitHub Secret值/让用户贴key/保存secret或key-hash、直推main/强推/绕过审查保护、删除无关用户改动/历史/账本/许可/原件、清日常浏览器数据。仅独立 Chrome 无头和隔离测试数据；不用 Edge/可见窗口/OS键鼠/文件对话框，不抢桌面焦点。真人 C15/C17 不在本轮执行或冒充完成。

## Stop conditions
本轮最多12个完整“实施＋对应验证”批次；共享请求/数据合同的原子业务纵向作为一个完整批次，最终同候选两轮回归合计一个验收批；修复/再次验证的实际批次保留，不按文件/调用/小任务拆分逃限，不重置历史计数。第12批仍未满足全部成功条件即停止施工，保存代码/用户数据/费用/原始失败与准确恢复前沿并向用户交接，不自动追加或缩减标准。同一阻塞连续两次没有新事实、有效修改或必要决定，停止该路径并给出最小区分动作；继续其他已授权且依赖成立的工作。
预算/次数任一到门、官方费用上界/精确型号/合法素材/安全凭据不可核即停止相应收费调用；Unknown只核对原任务，不自动重提、换模型/模式或释放预留，无 task 的同步 Unknown 保持未确证。需要新增权限/模型/重大依赖、不可逆操作、无法从仓库/原证据/官方资料解决的需求歧义，或真实像素不合格且额度不足、必要缺陷因果/正式依赖/可信HTTPS/实时保护不可达时，停止对应动作，明确实际证据、尝试与最小决定，保全可达成果。真实发布故障按当前事务处置，不把 finalize 清理问题一律当产品回退。用户要求停止立即收尾。任何必需验收缺失、间接或矛盾，不标 Goal 完成，不拿规划、旧成功、本地修好、CI数量或替身成品替代实际交付。
```

