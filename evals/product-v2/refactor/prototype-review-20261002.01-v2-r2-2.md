<!-- 拆分件 01/02 · 父文档 evals/product-v2/refactor/prototype-review-20261002.md -->
# V2.R2.2 · 可操作原型与交互验收冻结
[返回 prototype-review-20261002.md](prototype-review-20261002.md)

NOT-AUTHORITY: point-in-time V2.R2.2 prototype evidence; not a product implementation, release acceptance, dependency approval, or human walkthrough.

# V2.R2.2 · 可操作原型与交互验收冻结

输入：R2.1 `ui-baseline-20261001-chrome.md`（B01/G01/H01/H02/H03/V01，T7 缺口）＋ UI 合同 V2.UI.2（draft）＋ 不变量（context §6）＋ R2.3 `reference-review-20261001.md`（SEL-019）。
动作：资料确认、图片比较/返工、错误恢复的可操作浏览器原型；同 Shot 图片上下文、比较导航与信息摆放实测；必要确认保留；采纳项写回 UI 合同 §10 并冻结 §7.2 判据。
权限：计划 §3 后台自动化授权——独立临时配置 Chrome 无头（`154.0.8037.93`），四类 fake 上游，真 handler＋真 IndexedDB。不调用真实模型、不付费、不上传、不提交/推送、不部署。原型仅在 `?prototype=workbench` 隔离 launcher 加载，原型不得混入正式默认数据。

## 1. 原型实现（可移除，不碰产品）

| 文件 | sha256（前 16 位） | 说明 |
|---|---|---|
| `evals/product-v2/harness/workbench-prototype.js` | `aaa2dff6e0557b87` | 布局重组＋原生 dialog＋事实影响＋Unknown 分层＋焦点返回，全 174 行 |
| `evals/product-v2/harness/workbench-prototype.css` | `2c0ebc13794d5bef` | 仅原型样式，token 沿用产品 `styles.css` |
| `evals/product-v2/refactor/_prototype_smoke.py` | throwaway | 隔离无头验证脚本，跑完即证据，不进产品 |

工作树既有脏改（`app/product_v2/workspace.js` 等 M）为此前遗留，非本轮引入；本轮未改 domain/repository/产品 UI。原型行为：

1. 同 Shot 图片工作区：比较面板移入审核卡之后，参考/旧/新候选并排（`#prototype-image-plane`），返工/采用面板移入同一任务上下文，不再需要记忆另一屏。
2. 原生 `<dialog>` 包裹返工/采用面板：打开时把当前 Shot 的参考与候选克隆进对话框上下文，图片上下文不丢失；取消/关闭一律走产品原有 cancel handler（`rework-cancel`/`adopt-cancel`），不产生业务选择或提交。
3. 资料确认影响条：事实编辑后显示失效发送摘要名单（stale rows 名单＋“重新编译并人工确认后才能生成；已有候选与人工采用记录保留”），一键定位到生成阶段；不自动提交。
4. Unknown 分身份恢复：已知 task（有“核对任务”按钮）与无 task 显示不同解释，技术身份/错误收进 `<details>`，秘密不回显（本轮全 fake，无秘密）。
5. 焦点返回：返工/采用/比较关闭后焦点回到触发器；Escape 在 dialog 内转取消、在比较区转收起。

## 2. 无头验证：PASS（`prototype-smoke-20261002.json`，`ed417438…`）

`result PASS`，`finished_at 2026-10-01T17:27:15.983323+00:00`；`console_page_errors []`，`blocked_requests []`（loopback 外请求零放行），100 条请求全为本地静态与 capabilities。

| 场景 | 证据 |
|---|---|
| 单图返工隔离 | `shot_infographic_benefits` 返工后 1→2 候选；无关 Shot 记录相等、selection 记录相等 |
| 无 task Unknown | 无“核对任务”按钮，保留旧候选 1 个，不伪造查询 |
| 已知 task Unknown 核对 | 状态仍 unknown，submit 数 3→3，无重复提交 |
| 原生 modal Tab 包络＋Escape | 16 步 Tab 始终在 modal 内且焦点轮廓可见，Escape 回到 `rework-open`，比较区保留 |
| 事实编辑影响＋继续 | 4 张 Prompt 变 stale，影响条文本精确，候选/采用保留，submit 数不变，一键进生成阶段 |
| 刷新 | 记录逐字节相等，submit 数不变，快照 sha256 `a8055157…` |
| 响应式 9 面 | 1440/1366/390 × 理解/比较/生成，`scrollWidth ≤ width`，无 CSS zoom/transform 冒充 |
| 真 zoom 12 面 | 1440/1366 × 125%/200%（Chrome 设置页真实 zoom，非 CSS），`innerWidth ≈ w/z`，DPR 1.25/2，`visualViewport.scale=1` |
| 截图 4 张 | `prototype-compare-1440/-390/-native200`、`prototype-facts-1440` |

轨迹说明：smoke 自身 `trail` 为 reload 后读数＝0（预期，reload 后新页数组为空）；reload 前 27 次 click 完整轨迹在 `prototype-observations-20261002.json`（比较→返工→预览→提交→采用→取消→核对链），无多余业务点击——原型复用既有按钮，对话框新增的“预览/确认”属于 R2.2 要求保留的必要确认，不计入可删点击。

失败考古（均保留为证据，不删）：`prototype-keyboard-first-failure`（首版断言要求每步 `document.hasFocus`，撞上原生 Tab 末控件进 browser chrome 的真实行为）→ `prototype-native-focus-diagnosis`（8 步对照：BODY 失焦步 dialog 仍 `open+modal`，非后台化、非 dialog 重建）→ `prototype-settings-context-failure`（`chrome://settings` 在隔离上下文不可导航，Playwright 明确报错）→ 终版改用 persistent context 真 zoom＋Shift+Tab 恢复＋容忍 BODY 失焦步后 PASS。冻结结论：原生 dialog 的 Tab 包络判据是“仍在 modal 内＋焦点轮廓可见”，不以“每步都有 document.hasFocus”判定。

## 3. 问题→设计→冻结判据（对应 UI 合同 §10）

| 问题 | 原型设计 | 冻结判据（可测） | 落点 |
|---|---|---|---|
| H02 图片上下文/滚动 | 同 Shot 参考/旧/新并排工作区，比较入口紧邻任务卡 | 高频比较不依赖记忆另一屏；身份/版本/采用状态文本可辨；比较/采用入口不在整套长卡之后 | R6.2 / RC03 / §7.2 |
| H01 高频继续劳动 | 事实旁原始资料对照＋失效影响条＋重编入口 | 影响范围可见；必要确认保留；成功历史/人工采用不丢；不自动付费提交 | R6.1 / RC14 |
| H03 技术词/异常分支 | 已知/无 task Unknown 分层解释＋details | 已知核对不增 submit；无 task 明确不可查询与重提风险；错误给影响＋下一步 | R5.1 / R6.3 / §7.2 |
| B01 交付溯源错 | 比较区展示候选原 Attempt 身份（原型只读展示，未修产品） | 交付只读采用候选原 action 冻结 Prompt，不读当前编辑头；旧候选 manifest Prompt 与原 Attempt 相等 | R6.3 / RC16 / RC18（仍发布 blocker，本轮未修复） |
| G01 设置能力缺口 | 原型未做设置页（T7 缺口延续） | 设置仅展示可用能力与非 secret 身份；BYOK 内存；默认 key 不送用户目标 | R4.3 / R6.3 / RC08（未冻结，待 R4.1/R4.3） |
| V01 长卡视觉 | 固定比 `object-fit: contain`＋长文本渐进披露 | 测量只证可达/尺寸，不证真实商品对比质量 | R6.2＋真人走查 |
| 键盘/焦点/刷新 | 16 步包络、Escape 回触发器、刷新零重提 | §7.2 基线：焦点可见不被遮挡、关闭回触发器、保存/核对真反馈 | R6 / R7 / RC04（Edge/桌面/真人未覆） |

## 4. 可用商品套图结果：未成立（诚实结论，非证据缺口隐瞒）

当前候选是 fake 纯色测试图（R2.1 V01 已声明）；无真实生图 Adapter（R4.1 未评估、R4.2 未批准、无预算）、无真人验收、B01 未修。因此“得到一套可用商品图片”**无新鲜证据，RC09/RC18 不 proven**。本轮冻结的是验收 rubric（供 R4.2/R6.2/R7.1 使用，概念来源见 §5），不是能力证明：

| 维度 | 通过条件 | 证据形式 |
|---|---|---|
| 保真 | 与参考图一致特征，无结构/颜色/比例改写 | 原图对照人审＋VLM 提示（R6.2） |
| 文字 | 无错字乱码，无未确认文字 | 200% 逐字人核＋VLM 提示（R6.2） |
| 事实 | 卖点/参数与已确认事实一致，无虚构认证/数据/评价；无证据写 placeholder/未知 | 事实溯源（R6.1） |
| 尺寸/格式 | 命中平台规格阈值表 | 像素机检（R6.3） |
| 整套 | 数量齐全、风格 Lock 一致、角度/背景配额、参考身份统一 | manifest＋hash（R6.3） |
| 人审 | C17 签署＋C15 零介入非内置商品全链 | R7.2（self 审/截图/axe 不替代） |

