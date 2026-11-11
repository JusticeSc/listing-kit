<!-- 拆分件 01/04 · 父文档 evals/product-demo/d2-r1c/mock-product-2026-09-26.md -->
# D2.R1c 完整 Mock 产品交付记录（2026-09-26）
[返回 mock-product-2026-09-26.md](mock-product-2026-09-26.md)

# D2.R1c 完整 Mock 产品交付记录（2026-09-26）

> EVIDENCE-SNAPSHOT: implementation + developer rehearsal · NOT-AUTHORITY
> 权威任务与界面合同只在 docs/product-demo-goal-and-implementation-plan.md：§4.7（业务模型与单页交互契约）、
> §6.11.3A（FE-05–FE-08 工作包与九个界面状态）、§6.11.4（假动作标注）、§6.11.5（验收命令与失败路径）。
> 本文只记录本轮实际落盘了什么、跑了什么判据、观察到什么、仍未证明什么。零付费、零 provider 调用。

## 1. 本轮交付（FE-05 / FE-06 / FE-07）

| 包 | 落盘物 | 说明 |
|---|---|---|
| FE-05 前端骨架 | app/static/index.html、app/static/styles.css | 正式入口 / 提供；语义 form/fieldset/label、原生 button/radio/details/dialog；焦点可见、响应式栅格（宽屏三栏 + 底部交付栏，窄屏单列）、reduced-motion 降级 |
| FE-06 Mock service | app/static/mock-service.js、app/static/service.js | 页面只通过统一 service interface 读写；进程内状态机含正常/部分失败/Unknown 三种情形；动作按到达顺序排队；固定显示「离线 Mock · 不调用模型」 |
| FE-07 完整交互 | app/static/workbench.js | 输入→方案（可增删/排序/内联改）→一键整套（逐图离散状态）→候选→事实核对（F1–F8，机器项只读）→提示词版本→按原因单图返工→逐图选择→导出门禁与导出预览 |
| 正式入口 | app/server.py | / 提供单页；/static/*、/media/reference/*、/media/candidate/* 只读白名单；/legacy、/task、/workbench、/export、/act 保留 D2.R1 tracer 供回归 |

### 1.1 本轮发现并修复的真实缺陷（开发者预演产生）

**现象**：S2 保存新提示词（S2-P1 → S2-P2）后，旧候选 F-01 仍可「选为成品」；选中后 Shot 直接变 SELECTED，
交付栏把它计入有效选择并放行导出，导出清单把 S2 绑定到 F-01 · S2-P1（旧提示词版本的图）。

**合同依据**：计划 §4.7 —— 保存提示词新版本时「旧候选保留并标注来自旧版本；当前 Shot 变 STALE」；
「旧选择不计有效数」；「用户可重做并重新选择，也可显式恢复旧版本，使与旧候选绑定的选择重新满足当前版本」。

**修复**（mock-service.js / workbench.js / styles.css / evals/probes/mock_workbench.mjs）：
1. 交付有效性 = 候选绑定的提示词版本**正文**等于当前最新版本正文（candidateIsCurrent / selectionIsCurrent）。
2. 导出门禁新增阻断原因「<Shot> 的成品绑定旧提示词版本（S2-P1，当前 S2-P2）」；新增 getDeliverySummary，
   交付栏只统计有效选择，阶段位 recomputePhase 只按有效选择推进「可导出」。
3. 界面标注：旧版本候选显示「旧版本」徽标；被选中的旧版候选显示「✓ 已选成品 · 旧版本」。
4. 回归探针新增断言：选中旧版候选不计有效交付、导出 EXPORT_BLOCKED；返工后重选当前版本候选恢复有效；
   导出清单必须绑定当前版本候选。
5. 规则同时满足合同的「显式恢复旧版本」路径：把提示词恢复成与该候选绑定版本相同的正文后，该选择重新有效。

### 1.2 本轮发现并修复的真实缺陷（重置与在途生成竞态）

**现象**：在「一键生成套图」进行中点击页头的「重置演示」，页面会停在「阶段：逐图审核」，
而方案区显示「未生成」、候选区「等待候选」。走查说明承诺「页面上有一个『重置演示』，
任何时候点了都会回到刚打开的样子」，因此这是真缺陷。

**原因**：`reset()` 不进动作队列（`mutate`），它立即替换 `state`；在途的 `generateSet`
在 `await` 之间继续执行，最后把 `state.task.phase = "REVIEW"` 与 `currentShotId` 写到
重置后的新状态上（或在新状态上找不到 plan 而留下错误）。

**修复**：`app/static/mock-service.js` 的 `reset()` 改为走同一个动作队列
（`mutate("正在重置演示", …)`）：在途动作先收尾，重置最后执行并赢；`setScenario` 复用同一路径。

**回归与反向验证**：`evals/probes/mock_workbench.mjs` 新增 `resetDuringGenerateTrace()`：
生成中触发重置后必须 `plan=null / phase=INPUT / busy=false / operation=null / error=null`。
把 `reset` 临时还原成旧实现后探针退出码 1（`reset must not surface the replaced generation
as an error`）；恢复修复后逐字节一致、探针通过。

**浏览器复核（2026-09-27）**：真页面生成中点「重置演示」，最终回到「阶段：待确认资料」「未生成」，
页面无失败提示。

### 1.3 本轮发现并修复的真实缺陷（键盘核对后焦点丢失）

**现象**：键盘走到「商品事实核对」单选项，用方向键把 F4 从「未确认」改到「通过」后，页面重渲染，
焦点掉回 `body`；键盘用户要继续选 F7/F8 与视觉判断，得从页首重新 Tab。第一次键盘走查只改了
F4 一项就停止，所以此前没暴露；本轮全程键盘跑通时才被发现。

**合同依据**：计划 §4.7.8「控件 / 状态反馈」要求焦点可见并可用键盘逐项移动；每选一项就丢一次
位置，核对闭环对键盘用户不可用。

**修复**：`app/static/workbench.js` 给事实与视觉单选项加 `data-focus-key`
（`fact-<F>-pass|fail|unknown`、`visual-keep|redo|reject`），复用页面已有的 `preserveFocus`
机制；重渲染后焦点回到原选项。

**回归与反向验证**：
- 浏览器复核：Tab 到 fact-F4（当前 unknown）→ 方向键 → F4=pass，且 `document.activeElement`
  是 `fact-F4-pass`；随后 F7/F8/视觉判断可以连续用键盘选择，不再回到页首。
- 入口自检新增两个锚点判据（`data-focus-key="fact-${attr(fact.id)}-pass"`、
  `data-focus-key="visual-keep"`）；删掉 pass 锚点后 `app/server.py --check` 退出码 1
  （「正式单页缺少键盘焦点保持锚点…」），恢复后文件逐字节一致
  （`app/static/workbench.js`：`211389B7E66A2B26` → `CF5072F317545D25`；
  新增判据后的 `app/server.py`：`0C9D445B50426AE4`）。

