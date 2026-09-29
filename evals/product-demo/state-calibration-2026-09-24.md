# 之前工作审计与当前状态校准

时间：2026-09-24T17:40:26+08:00  
范围：完整演示产品 Goal、Phase 0 产物、刚开始的事实卡通用化、控制面一致性  
结论：**D0.1 可保留为已完成；D0.2–D0.8 均未完成；系统 Goal 当前为 paused；尚未形成可用的新演示产品。**

本文件是审计时点证据，不替代 `docs/product-demo-goal-and-implementation-plan.md` 的目标合同，也不替代
`_working/amz-listing-kit-product-demo/state.md` 的当前执行状态。

## 1. 当前事实

| 声明 | 当前证据 | 审计结果 |
|---|---|---|
| 系统 Goal 可执行 | Goal 工具直读：id `01a0ca17-2179-7eb0-969a-af9c79c4d8ca`，status `paused` | contradicted；旧 state 写 `active` 已校准 |
| D0.1 已选定权威设计 | `d0-1-selection.md`、A/B/C 原图、请求快照与账本；C 的原图哈希仍存在 | proven |
| D0.2 已冻结参考包 | 已有 C、upper-closeup、lower-detail 三张可用源图，但 `fixture-design/pack/`、`reference-board.png` 与冻结清单不存在 | missing |
| D0.3 已冻结事实卡 | `demo/fixture/aster-01/product.json` 已存在；manifest 与阈值派生记录不存在，卡也未被参考包版本绑定 | indirect |
| 事实卡已经成为运行门禁 | `factcard.py` 有求值器；`measure_f1_f8.py` 的 CLI 没调用它，永远返回 0，报告仍写 v2 | contradicted |
| P1 换商品零改代码 | 没有第二商品；量测器仍硬编码 teal/sleeve/orange、盖/筋/底圈以及 Aster 报告文字 | contradicted |
| P2 负样本必拦 | 没有负样本、未变异对照、逐谓词断言或漏报/误报统计 | missing |
| P3 阈值派生 | 最终阈值从 D0.1 表人工写进 JSON，但没有可复算派生规则、样本版本和过期判据链 | missing |
| P4 真实商品同路径 | 没有真实商品素材 | deferred；不计入当前演示 Goal |
| 新产品已经可供陌生人使用 | `demo/` 目前只有夹具与量测脚本，没有新工作台、状态库、真实 I2I 产品入口、审核返工或导出链 | contradicted |
| 旧 v2 功能基线未被破坏 | 校准前状态/文档/快照检查通过；校准后控制探针有意变化，完整回归因内存余量不足被运行器拒绝，旧 manifest 因此失效 | unverified；需在安全内存条件下完整回归后重建快照 |

## 2. 新鲜运行证据

2026-09-24 17:35–17:40 重新运行：

- `factcard.py` 与 `measure_f1_f8.py` 可编译；
- A/B/C 可重新量测，结果写入 `evals/product-demo/_audit_v3/`；
- v2→v3 的高宽比和筋条数不变，但颜色分类造成上段占比与橙环占比漂移：
  A 上段 `0.6603 → 0.6555`，B `0.6819 → 0.6673`，C `0.6543 → 0.6479`；
  B 橙环 `0.0147 → 0.0138`，C `0.0154 → 0.0136`；
- 直接调用事实卡求值时：A=`manual`，B=`pass`，C=`manual`。C 因
  `upper_color_delta_e=13.66` 超过 pass `12.0` 进入人工档。

这组结果说明新分类器能运行，但尚不能证明它更正确。尤其 B 曾因“顶面暗凹像开口”被人工排除，
机器整体 `pass` 只表示现有机器谓词没有覆盖该缺陷，不能替代人工 F4/F7。

控制面校准后又运行了状态守卫、17 向状态反向探针和文档守卫，三者均通过。随后运行完整回归时，
运行器检测到可用物理内存 `4,327 MB`、可用提交 `7,893 MB`，低于安全门槛 `5,000 / 9,000 MB`，
以退出码 8 拒绝执行。未使用 `--force` 绕过保护。因为 `evals/probes/project_state.py` 已有意修复，
旧 `v2_baseline_manifest.json` 当前同时报告代码树变化与回归报告哈希变化；必须等完整回归实际通过后再刷新。

## 3. 代码级发现

1. `measure(path, card=None, clf=None)` 暴露了 card 参数，但 `_check`、`declared_of`、`pass_max`
   仍读取模块级 `CARD`；传入另一张事实卡不会完整生效。
2. 主量测逻辑仍以 `teal`、`dark/sleeve`、`orange`、lid、rib、bottom ring 组织。
   这可以作为 `cylinder-v1` 的商品族适配器，但不能称为换任意商品零改代码的通用层。
3. CLI 没有 `--card`，没有调用 `fc.evaluate` / `fc.format_report`，没有按 `EXIT` 返回，
   报告标题仍是 v2，筋条目标仍直接写 `3`。
4. `load_card` 只检查 schema 名称，不验证角色、metric、阈值区间、重复事实 id 或缺失字段。
5. `_NEUTRAL_L_WEIGHT=0.35` 被注释称为类目通用，但当前没有跨商品证据；应登记为待校准算法参数。
6. 当前只有正样本参与阈值设置，不能估计拒绝能力与误报率。先加负样本再扩大工作流是必要顺序。

## 4. 资产与成本状态

- 账本共有 7 次可计费调用：3 次 T2I 设计候选，4 次 I2I 视图尝试；
- 当前冻结候选应只采用 C 正面全身、ref-02-upper-closeup、ref-03-lower-detail；
- ref-02-three-quarter 是探针，ref-02-upper-detail 是失败尝试，均不进入冻结包；
- D0.2 接下来只做复制、哈希核对、manifest 和参考板，不再调用模型。

## 5. 校准后的状态与下一动作

- 系统 Goal：`paused`；
- Phase -1：历史上已完成，相关证据仍有效，但不能证明当前 Goal 仍 active；
- Phase 0：`pending`，G0 未通过；
- 已完成任务：D-1.1–D-1.4、D0.1；
- 待完成：D0.2–D0.8；
- 唯一下一动作：Goal 再次进入可执行状态后完成 D0.2，使用已有三张图冻结最小参考包，不生成新视图；
- 进入 Phase 1 前必须完成 P1–P3；P4 明确后置。
- 工程验证阻塞：释放足够内存后串行运行完整回归，再重建 v2 基线快照；当前不得宣称回归全绿。

## 6. 本审计没有证明什么

它不证明事实门已经可靠、不证明第二商品可用、不证明 `qwen-image-3.0` 场景候选满足 F1–F8，
不证明陌生使用者可以完成任务，也不证明真实运营提效或 Amazon 审核通过。
