<!-- 拆分件 02/04 · 父文档 evals/product-demo/d2-r1c/mock-product-2026-09-26.md -->
# 2. 判据与命令证据
[返回 mock-product-2026-09-26.md](mock-product-2026-09-26.md)

## 2. 判据与命令证据

| 判据 | 命令 | 结果 |
|---|---|---|
| 状态机轨迹（正常/部分失败/Unknown、重放一致、单图隔离、旧版绑定门禁、生成中重置） | node evals/probes/mock_workbench.mjs | 通过（含 §1.1 / §1.2 新增断言）。输出：deterministic replay, plan direction compiled into prompt, discrete states (no fabricated percentage), partial/Unknown preserved and isolated |
| 进程自检（零网络、零写盘、单页五区可取数、Mock 轨迹、键盘焦点锚点） | uv run --with-requirements requirements.txt python app/server.py --offline-fixture demo/fixture/aster-01 --check | 退出码 0；最近一次读数 7.4s、10960 个文件路径/大小/修改时间未变、26 个关键文件逐字节未变；输出含「正式单页：5 个业务区域 + service interface + 固定 Mock 边界」。焦点锚点判据有反向验证：删掉 pass 锚点后退出码 1。文件总数随仓库证据文件新增而变（此前 9.0s 那次是 10959） |
| 假动作标注 | 浏览器逐句观察（§3；2026-09-27 又复核一次）+ `evals/probes/walkthrough_brief.py` 的落点判据（真 HTTP；说明引用的句子必须在单页/渲染代码里逐字找到，5 向反向对照） | 一键＝「一键执行当前整套方案。离线演示，不调用模型。」；返工＝「离线演示：不调用模型，不写文件；这里只模拟状态变化，不产生真实新候选。」；导出＝「离线演示：未写出任何文件。该清单用于验证交付结构，不是文件下载。」；候选卡分别标注 交互夹具 / 历史真实候选 / Mock 新候选 |

关于「整套进度」：方案区保留整体进度条，其值是「已落定 Shot 数 / 总 Shot 数」的真实推导
（READY/SELECTED/FAILED/UNKNOWN/STALE），不是伪造百分比；逐 Shot 已无百分比字段（探针断言 `!("progress" in shot)`）。
页面可见文本在生成中与完成后均不含任何 `%` 字样。

## 2.1 §4.7 动作矩阵的实现对照（代码 + 浏览器/探针证据）

| 动作 | 实现位置 | 验证方式与观察 |
|---|---|---|
| 生成推荐方案 | workbench.js submit#input-form → mock-service.createRecommendedPlan | 浏览器：未勾选核对不能生成；勾选后 4 张计划图（DRAFT） |
| 调整方案（增/删/排序/内联改） | updateShot / addShot / removeShot / moveShot + plan-edit-form | 探针：方向编译进默认提示词，`PURPOSE_REQUIRED` / `SHOT_DIRECTION_REQUIRED` 阻断；浏览器：空方向报错并把焦点送回字段 |
| 一键生成套图 | data-action=generate-set → generateSet | 浏览器：整套一次执行、逐图离散状态、4/4 候选；探针：`ALREADY_GENERATED` 防重复 |
| 保存提示词新版本 | submit#prompt-form → savePrompt | 浏览器：S2-P1→P2、旧候选保留并标「旧版本」、Shot 转 STALE；探针：缺事实锁锚点 `FACT_LOCK_BROKEN`、无变化 `NO_PROMPT_CHANGE` |
| 选为成品 | data-action=select-candidate → selectCandidate | 浏览器：事实未全通过时按钮禁用并列出尚缺项；旧版本候选可记录但不计有效交付 |
| 重做这张 | submit#rework-form → reworkShot | 浏览器：scene 只对目标 Shot 产生新版本+新候选；identity 阻断；探针：`REASON_REQUIRED` / `DIRECTION_REQUIRED` / `RECONCILE_FIRST` |
| 核对运行状态 | data-action=reconcile-shot → reconcileShot | 浏览器：Unknown 只给核对入口，核对后转失败并可返工；探针：`NOT_UNKNOWN` |
| 导出套图 | data-action=export → exportDelivery + getExportBlockers | 浏览器：未选齐 / 旧版绑定 / STALE 均禁用并给出原因；导出仅有预览清单，0 个下载链接 |
| 切换演示情形 / 重置 | setScenario / reset | 浏览器：normal / partial / unknown 三情形可重置复跑 |

边界：Mock 未建模成本或预算，合同 §4.7 的「预算允许 / 超过预算阻断」只在 Phase 4 真实调用阶段出现。

## 3. 浏览器实测（开发者预演；http://127.0.0.1:8778/ ，CDP 禁用缓存后硬刷新）

### 3.1 正常闭环（本轮复跑，含 §1.1 修复后的判定）

1. 初始态：阶段「待确认资料」；方案/检查/交付三区空态；导出禁用并说明原因。
2. 勾选「已对照参考图核对资料」→ 生成推荐方案 → 4 张计划图（S1 主图·正面全身·纯白背景正面平视；
   S2 场景图·正面全身·浅色石材台面三分之四；S3 杯盖细节·杯盖近景；S4 防滑套细节·底部近景），
   每张卡显示 必需图/参考视图/画面方向；方案 v1 DRAFT。
3. 一键生成套图 → 逐图离散状态推进，完成后 4/4 待检查（S1 1 候选 C-S1-01、S2 2 候选 F-01/F-02、
   S3 1 候选、S4 1 候选）；页面无百分比文本。
4. S1 核对 F4/F7/F8 通过 + 视觉保留 → 选为成品 → 交付栏「必需图 1/4」，其余图列入未选定清单。
5. S2 展开完整提示词 → 保存新版本 → 摘要变「完整提示词 · S2-P2 · 已修改」；F-01/F-02 原样保留、
   卡上出现「旧版本」；Shot 状态「提示词已更新 · 2 旧候选」；交付栏出现「S2 尚未选定成品；S2 状态为 STALE」，
   导出禁用。
6. （修复验证）把旧候选 F-01 核对通过并选为成品 → 卡显示「✓ 已选成品 · 旧版本」；
   交付栏仍为「必需图 1/4」并给出「S2 的成品绑定旧提示词版本（S2-P1，当前 S2-P2）」；导出仍禁用；
   live region 说明「已选定 S2，但该候选绑定旧提示词版本 S2-P1，不计入交付…」。
7. 场景返工：选原因「场景/构图」后显示影响说明「将改变：当前图的场景、构图、光线与提示词可变段（会再调用生图模型）；
   不会改变：商品事实锁、其他计划图、已保留的旧候选。」→ 提交 → 新增候选 C-S2-R1 · S2-P3
   （标注「Mock 新候选 · 未调用模型」）；S1/S3/S4 候选数与选择未变；提示「只返工了 S2；旧候选仍在，其他计划图没有重跑」。
8. 核对新候选并选为成品 → 交付栏恢复有效计数（2/4 → 3/4 → 4/4）；导出可用。
9. 导出预览：01-S1.png（S1 · C-S1-01 · S1-P1）、02-S2.png（S2 · **C-S2-R1 · S2-P3**）、03-S3.png、04-S4.png；
   标注「离线演示：未写出任何文件。该清单用于验证交付结构，不是文件下载。」；阶段「导出完成（Mock）」；
   页面无 `a[download]` 链接。
10. identity 阻断复验：对 S1 选原因「商品失真」→ 提交被拒（「商品身份错误不能靠追加场景词解决；正式产品会转到
    参考资产/模型路线核对。」），候选数与 S1 状态不变。

### 3.2 部分失败与 Unknown（本轮复跑）

1. 切到「部分失败」情形并重置 → 方案 4 张 → 一键整套。
2. 结果：S1 待检查·1 候选、S2 待检查·2 候选、S3 失败（「Mock 失败：本镜位未产生候选；其他图片已保留。」）、
   S4 Unknown（「Mock Unknown：不知道请求是否完成，禁止直接重提。」）；方案状态「v1 · 部分完成」。
3. S4 详情只有「核对运行状态」，没有返工表单/重做按钮（无法直接重提）；点击核对后 S4 转「失败」并出现返工表单，
   提示「已核对：没有发现可用候选，状态改为失败；现在可以安全返工目标图。」。
4. （本轮补跑）S3 选「场景 / 构图」并写方向后提交 → 新增候选 C-S3-R0 · S3-P2；
   S4 选「尺寸 / 白底」并写方向后提交 → 新增候选 C-S4-R0 · S4-P1；S1/S2 候选与选择未变。
5. 四张逐一核对选定 → 交付栏 4/4；导出预览四行：01-S1.png（S1 · C-S1-01 · S1-P1）、
   02-S2.png（S2 · F-01 · S2-P1）、03-S3.png（S3 · C-S3-R0 · S3-P2）、04-S4.png（S4 · C-S4-R0 · S4-P1）；
   标注仍为「离线演示：未写出任何文件…」，页面无下载链接。
6. 复位回「正常」场景初始态。

