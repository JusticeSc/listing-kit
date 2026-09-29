# D2.R2a 界面语言打磨证据（2026-09-26）

## 改了什么（只动展示说法，不动判定逻辑）

- `demo/core/back_chain.py`：REWORK_ROUTES 两处展示串转业务语言。
- `app/views.py`：新增 SCENE_LABEL / COMPOSITION_LABEL / VARIATION_LABEL / VIEW_LABEL /
  CHECK_RULE_CN / REVIEWER_CN / SELECTED_BY_CN + `_lab` 兜底（不认识的代号原样保留）。
- 任务页、计划页、候选页、合成页共 10 处渲染点接入映射；S1–S4、F-01、F1–F8 保留。
- 合成页命名规则空值显示"未定"，不再留空白格。

## 验证（全绿）

- `app/server.py --check`：退出码 0。
- `evals/probes/walkthrough_brief.py`：25 条落点全过。
- `evals/probes/offline_app.py`：6 组全过。
- `evals/probes/offline_failures.py`：7 组全过。

## 真人走查对照（本机实走：确认方案→改提示词→返工→选中 F-01→导出）

- 计划页：场景/构图/参考图全部中文；来源三行无路径无哈希。
- 返工页：对照表无 ShotSpec / PromptVersion / PC-12。
- 候选页：检查项中文；评审人显示"操作者自签（非第三方）"。
- 合成页：事实结论"人给的"、选的人"本次走查的操作人"。
- 导出页：S2 行显示已选定（与候选编号同行，不同单元格）。

## 说明

- 走查用一句英文追加提示词（传输限制），属一次性内存状态，不落盘。
- state.md 未动，请按控制面流程补进度指针。
