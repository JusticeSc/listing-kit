NOT-AUTHORITY: point-in-time Goal recovery and G2 reconciliation; not product completion, dependency approval, paid-call authority, or release acceptance.

# Goal 恢复与 G2 核对 · 2026-10-02

## 真实观察

当前 Goal 工具实际返回 active，原生 ID `1595e928a065b786`；完整原始展示体与工具对象保存在 `goal-observation-20261002.json`，观察时刻 `2026-10-02T02:30:13.139Z`。原生 ID 是 16 位十六进制 handle，不补造成 UUID，不继续声称接口没有 ID。未调用 create/resume/complete/drop。

用户重新设置并粘贴完整目标，正文只要求桌面 Chrome、取消历史版本兼容，保留 RC01–RC20、两个真实模型、人审、V1 专批及各自权限门。计划 §2.1 保存可读正文，原始展示码/边框仅作展示归一；正文 SHA256 `e5a10fd4b69cdde75c510e96dd309ed2e724690f1ca5f49ef2ef78ecb938080f`。旧观察和原目标快照原样保留，不用旧读数声明本会话重读。

## 已有成果与断点

没有重置已完成任务或删除用户工作区改动。恢复断点仍是 V2.R3.1，Phase 0–2 的已有证据继续保存；最终版本必须取得新鲜证据，不能从历史 PASS 推导最终完成。

## G2 冲突的事实与处置

当前 state 把 Phase 2 标 done、next 指 R3.1；旧时点 `prototype-review-20261002.md` §8 则建议 Phase 2 active、G2 递延、next R4.1。R2.1 七任务已审计，T7/G01 被准确记录为缺失设置能力，而非通过；R2.2 已提供资料/比较返工/Unknown/焦点与刷新原型，设置形态未冻结；R2.3 已固定来源和许可。审计结论齐备不等于尚未实现产品能力通过。计划 §2.4 明确该区别，保留设置交互的 R4.3/R6.3 门与 RC07/RC08/RC10/最终人审；旧报告作为历史不重写，不把其时点建议当成当前进度。

B01 交付溯源、boot 间歇根因、真实第二模型、默认消费策略与 C17/C15 仍未闭合。本记录不消除任何发布 blocker。

## 实现与验证范围

恢复守卫需接受工具实际返回的原生 ID，并核对 v2 required 绑定的观察 ID/目标/时刻；session 只用于接口确实无 ID。展示归一只识别已观察的两类 `[13;28;13;0;0;1_`/`[13;28;13;1;0;1_` 码和行首 `▏`/`│`，不吞普通正文标点。恢复脚本改为报告“仓库保存的最近观察”，不冒充本次脚本查询 Goal。

改前探针实际输出 `native_goal_id_accepted=False`、`presentation_noise_removed=False`。改后状态守卫退出码 0；状态反向探针 62 向全部匹配，路由反向探针 14 向全部匹配并逐字节还原；冷恢复实际输出 required/native ID/next R3.1，且明确“不查询系统 Goal”。文档守卫 `--no-run` 退出码 0（不证明所有文档命令执行）。期间暴露的历史 superseded 记录误套新证据要求、prepared 夹具残留观察、README 中性“下一任务”文案误报均已针对机制修正；未靠重跑掩盖。

## 快照

改前权威/守卫/探针字节与 SHA256：`_stage-amz-control/goal-rebind-20261002-20261002-023013139/hashes-before.json`。后续指纹在同目录补入。恢复控制工作未付费、上传、提交推送、部署或删除 V1；后续前端检查器获用户单独批准，安装证据另见 `frontend-approval-20261002.json`，不把其授权倒灌为其他权限。
