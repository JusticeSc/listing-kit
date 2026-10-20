# 停工收尾：批次18 可选图刷新（2026-10-20）

用户指令：**即刻停止当前工作，做好收尾准备**。以下是停工时的准确状态，供恢复时判断
「什么已完成、什么没开始、什么必须重新核验」。本文件不是授权，也不构成任何验收。

## 停工前实际在做的事

在 **PR #21（`chore/walkthrough-zoom-keyboard-20261020`）** 的零收费收尾之上，准备用户
已选的「先花额度刷新两张 stale 图」：`shot_infographic_benefits`、`shot_detail_material`。
费用上界仍按用户口径 ≤1 元（实际未花）。

## 已完成（可复用）

| 事项 | 证据 |
| --- | --- |
| 5 条 Codex 复核意见全部修复并回复/解决 | PR #21 提交 `f5e1e17`；threads 已 resolved |
| 缩放段改为如实口径（CDP 等价视口 ≠ 原生 zoom），原生 zoom 验收**保持未验** | `tools/rehearse_v273_walkthrough.py`；`evals/product-v2/v273-rehearsal-20261020-091407.{json,md}` |
| 键盘逐步遮挡检查、两包各自对照门禁已采用集合、报告 JSON 不再截断、每段关键操作可命中 | 同上（八项关键操作在 1.25×/2× 均 found+visible+in_view+hit_self） |
| 第17批冻结两轮回归 | `evals/product-v2/v2.7.1-regression-20261020-v271-frozen-6e692a4c-final.{json,txt}` |
| 真实项目包的 stale 事实被实测确认 | `gate-snapshot.json`（只读快照：`b16_import_host.py` 的 refusing provider，0 次调用）：`shot_infographic_benefits`、`shot_detail_material` 在交付门禁为 `stale`（已采用（已过期）），其余三张 `current` |
| stale 根因定位 | `gate-snapshot.json` 的 `confirm_parts.blockers` 原文：「#2 卖点信息图 · DECISION_REQUIRED 这张图还没有决定要不要印文字…返回：shot_spec」——#9 印字决定上线后这两张图缺这一步决定，因此 Prompt 无法编译、采用过期 |
| 交付门禁与导出的实际关系 | 同一快照 `export_enabled=true`：两张 `stale` 不阻断交付导出本身（不是产品 bug，`stale` 是采用当前性问题）；但「五张不同用途的可用图」不成立，不能用这次导出冒充批次18 成品 |

## 未开始 / 未完成（恢复时的起点）

1. **没有发生任何真实模型调用**：`record_host.py` 只记录出站形状并在进程内拒绝外发，
   0 次付费、账本未变动（仍 4/12 图、0/4 辅助、0.56/5 元）。
2. **没有产生新的出站形状记录**：`recorded-shapes.json` 不存在——计划阶段的选择器在停工前
   刚修正到 `#shot-spec-list .shot-spec[data-shot-id]`，最后一轮探针被停工打断。
   早前一轮留下的 `capture-result.json` 被下一轮脚本开头的 unlink 清掉、随后进程被杀，
   **原始文件已不存在**；同一事实改用只读的 `gate-snapshot.json` 重新取证，未按记忆回填。
3. **两张图仍未刷新**：交付门禁仍是 2 `stale`；批次18「线上真实五图/两包」不成立。
4. **PR #21 未合并**（已转回 Draft），main 未因此变化；收工时 `f5e1e17` 的 CI 运行
   `39352437953` 仍 `in_progress`，而收尾提交 `4321ed0` 又触发一次新运行。
   **两个运行的结论都没有被观察，都不得当作通过。**
5. 收尾时 `mergeStateStatus=BLOCKED`，原因未继续排查（停工即停手）。

## 恢复时的最短路径（按产品自身入口，不写专家稿）

1. 计划阶段：`#shot-spec-list .shot-spec[data-shot-id=<shot>]` 内
   `#spec-print-selected-<shot>` → 勾 `#spec-text-<shot>-<slot>`（`MAX_ON_IMAGE_TEXTS=4`
   按条目计）→ 卡片内「保存」。印字候选来自已确认且绑定到该图的事实，界面只做呈现。
2. 制作阶段：选中该图 → `#rework-open` → 问题分类（产品固定词表）+ 一句普通中文方向 →
   `#rework-preview` → `#rework-submit`；等待该图 attempt 落定（recording host 会记
   出站形状后拒绝外发，真实 host 才外发）。
3. 采用新候选 → 交付阶段整套检查 → 导出交付包与项目包 → 独立导入核对 + 账本记账。

## 收尾清理核对

- 两个后台任务（CI 轮询、形状捕获）已取消。
- `5516` 无 LISTENING（仅剩 TIME_WAIT 客户端套接字）；无遗留 `record_host.py` / Chrome 进程。
- 5 个 `b18-capture-*` 临时 profile 已删除。
- 本目录下 `capture_shapes.py` / `record_host.py` 是**一次性控制面工具**，未进入产品源码，
  也未加入任何账本或验收记录。
