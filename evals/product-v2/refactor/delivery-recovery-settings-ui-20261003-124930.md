# V2.R6.3 · 交付/错误/设置 - 工作证据

> CONTROL-STATUS: current · NOT-AUTHORITY（时间点证据；C17/C15 人审与真实付费链不属本切片）
> Goal: docs/product-v2-refactor-plan.md §2.1（sha256=3f9f1842d67d063fa9d8cfbbaf60eb5971fe24b46502c97455241ccac40d4607）
> 日期：2026-10-03；报告戳：20261003-124930（与迁移报告同戳；交付报告 124831）

## 1. 切片动作（唯一事实来源：仓库 diff + 验证器）

- 修复 B01/RC16 交付溯源错：`app/product_v2/workspace.js` 交付装配不再读当前编辑头 `promptRecordOf(shot_id)`，改为读被采用候选原 action Attempt 冻结的 `prompt{version,hash}`。旧候选 + 新编译头并存时，manifest 不再把当前头版本误记到旧候选上。
- 验证器加回归：`tools/verify_v2_6_2_delivery.py` 的 `walk_to_deliver` 在交付前于生成阶段重编译首张图（当前头前进），`V2.6.2-04` 新增 `provenance_ok` 断言：manifest 每图的 prompt_version/hash 必须等于该 attempt_action 原 Attempt 冻结值；新增 `b01_manifest_provenance` 探针（IndexedDB generation_attempt 按 action 取最新）。
- 未动语义：Attempt 冻结字段、候选身份、manifest 形状零变化；修的是“取数来源”，不新增 provenance store（与 R2.3 结论一致：用已有原 Attempt 冻结字段，删错误查询点）。

## 2. 验证（本轮实跑，全绿）

| 验证器 | 证据 | 结果 |
|---|---|---|
| V2.6.2 交付门禁 | evals/product-v2/v2.6.2-delivery-20261003-124831.txt | 全过；-04 含 B01 回归（重编译首图后 manifest 仍记冻结版本） |
| V2.6.3 项目迁移 | evals/product-v2/v2.6.3-transfer-20261003-124930.txt | 全过；迁移后返工→门禁→交付闭环 |
| V2.6.4 可访问性 | evals/product-v2/v2.6.4-a11y-20261003-123202.txt | 全过（R6.2 同日证据复用；本切片未动 UI 结构） |

## 3. R6.3 验收对照（plan §V2.R6.3）

- 包 hash/manifest 可追溯 -> 6.2-04（ZIP 独立核对 + B01 溯源回归）、6.3-04/05/08（项目包往返逐记录保留）。
- 错误不藏，核对不重提 -> 6.2-08/09/10/12（字节缺失阻断、套件缺失定位、Unknown 确认解锁）。
- 默认 key 不在 DOM/响应/包/日志 -> R4.3 已冻结（BYOK 头内存态、redact、导出白名单 + 负向审计）；本切片交付包/项目包不新增秘密字段，6.2/6.3 全过。
- 390/缩放/focus 成立 -> 6.4 全过；交付阻断定位入口聚焦点到运行按钮（6.2-12）。
- 失败：禁交付有硬缺口但不删除项目，不偷用当前 key 查旧 task -> 门禁阻断不删数据、无 task 不盲目重提（6.2-08/10，R5.1 Unknown 语义延续）。

## 4. 保留缺口（不属于本切片）

- 设置页（T7/G01）仍缺：R4.3 服务端 BYOK/默认档/出站策略已落地，本切片未新增设置 UI；能力展示仍为生成执行区的 provider 身份行与 capabilities 错误文案。
- V2.R7.2 C17/C15 人审仍待执行；R4.2/R5.2 真实付费证明仍 blocked。
- B01 对应 state blocker `release_blocked_delivery_manifest_uses_current_prompt_for_old_adopted_candidate_follow_V2.R6.3_RC16` 本切片修复后可关闭（见收尾 state 更新）。
