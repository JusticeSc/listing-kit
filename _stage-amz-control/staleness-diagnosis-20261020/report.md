# 两张 stale 图：诊断（零收费）与刷新执行（2 次已预留调用）

## 结论

两张图**不是**因为商品资料、事实、规格或风格变化而过期。它们过期有三条各自独立的原因：

1. **模型切换（两张都有）**：项目当前图像模型是 DashScope `qwen-image-3.0`（其余三张采用图也是 qwen），
   而这两张采用图是用火山 `doubao-seedream-5-0-flash-260915` 生成的。当前性按 Provider 档全等比较，
   模型不同即过期。
2. **旧记录没有冻结编译器规则版本与商品资料版本（两张都有）**：冻结记录缺
   `compiler_rule_version`、`intake_version`，系统无法证明它按当前规则/资料准备过，按合同判过期。
   采用时的请求快照里商品资料已是 v4（当前也是 v4），所以这不是资料内容变化。
3. **返工血缘在重新准备时被丢弃（仅细节图，且是一个真实缺陷）**：细节图采用版本是 edit_candidate
   （参考图 = 问题候选 + 商品原照，正文 1098 字）；当前 head（v11/v12/v13）是 regenerate_original
   （参考图只有商品原照，正文 691 字）。原因是 `prompts.prepare()` 走 `compileAndSave(shotId, {action})`，
   从不传 `reworkLineageOf(record)`，所以对带冻结血缘的系统稿重新准备会**静默改变请求模式与参考图组成**。
   对照：人工全文路径 `prompts.reconfirm()` 会保留血缘（`basisWithLineage` / `lineageReferencesOf`）。

## 证据

- 采用身份（选择记录 → 候选 → 同 action 的 attempt → prompt.version/hash）：
  - 细节图：`act-e03c2644480d449182a7f0001cc1a8be`，prompt v4，hash `499899461776…`，edit 模式，1098 字，ark。
  - 卖点信息图：`act-490a5961ab94432e8bb84cd0fbd2b4b1`，prompt v17，hash `6301137656e1…`，人工全文 959 字，ark。
  - 其余三张：main v16 / scene v17 / dimensions v17，均为 qwen。
- 依据逐字段比对（`basis-diff.json`）：两张的 shot 签名、风格/套图/单图规格版本、平台、Provider 档与采用时一致；
  差异只有 `compiler_rule_version`（stored null → current 3）与 `intake_version`（stored null → current 4）。
- 真实界面复核（`prepare-evidence.json`，隔离 profile + 拒绝外呼的宿主）：
  - 把信息图印字决定改为「不印新增文字」：规格 v9 → v10，保存成功（用户 2026-10-20 的选择）。
  - 细节图点「重新本地准备」：v12 → v13，hash `a445acb30908…`，仍为 regenerate 模式（血缘没有被带回）。
  - 信息图点「按当前依据确认此人工全文」：v17 → v18，正文保留，但 hash 变为 `d4603ff8bcd3…`
    —— 因为当前 Provider 是 qwen；v15/v16 的 d460 也是 qwen，v17 的 6301 是 ark。
- 交付门的实现（`review-delivery.ts:121-126`、`selection-adoption.ts:155-160`）按 **attempt 里冻结的
  prompt 版本**取样，再判该版本的过期；重新准备只会产生新版本，不会让已采用图恢复 current。

## 因此

- 让两张恢复 current 的现实路径是**在当前模型（qwen）下各重新生成一张并重新采用**；
  重新准备/重新确认都不改变已采用版本的绑定，不能零付费修复。
- 重新发送的准入（`domain/confirm.js` 的 `submissionModeAllows`）：已有 succeeded 的图不能走普通确认单，
  只能走返工（`rework`）——改候选或按原资料重画；两条都已预留形状由宿主传输层硬限制。
  返工预览会带冻结血缘（`previewManualForRework` / `compile({rework})`），所以这条路径本身不会丢模式。
- 细节图的模式漂移是独立缺陷，已记录：修复点是 `prompts.prepare()` 应像 `reconfirm()`/返工预览一样带
  `reworkLineageOf(record)`，并用合同测试锁住「带血缘的系统稿重新准备后 mode/参考图不变」。

## 执行结果（同日下午，按用户选择题与两条预留调用）

用户 02:59 恢复正式开发并要求把待办转成选择题；本轮选择题的回答是「信息图不印新增文字」「两张 stale 图各重生成一张再采用」。
两次预留调用各执行一次，未重试：

| 图 | 预留 | 真实出站 | 新候选 | 采用后门禁 |
|---|---|---|---|---|
| 细节图·材质工艺 | `b19-detail-refresh-01` | HTTP 200 · qwen-image-3.0 · prompt v13 · `1344*1344` | `act-021de106…` v3 · sha `ea50b044…` | current |
| 卖点信息图 | `b19-infographic-refresh-01` | HTTP 200 · qwen-image-3.0 · 返工 keep_manual · 959 字 | `act-893b00e5…` v8 · sha `2fa38cd6…` | current |

- 两张都必须走**返工**（已有 succeeded 不能走普通确认单）。人工全文的信息图第一次预览后才会出现
  `#rework-prompt-choice`，必须显式选 `keep_manual` 再第二次预览，正文才保留 959 字。
- **采用作用于当前正在查看的候选**：返工提交后比较面板仍停在旧候选，此时点「采用」只会给旧候选再写一个
  选择版本（实测留下 3 个都指向 `act-e03c26…` 的选择版本、门禁仍 stale）。先把查看切到最新候选再采用，才写出
  `act-021de106…` / `act-893b00e5…`。
- 门禁五张全 `current`；整套检查过期后重跑本地确定性检查＝阻断 0/高风险 0/提醒 0/未知 0（视觉复核可选未跑）；
  交付包 `b19-exports/b19-delivery-final.zip` 导出，`checks.json.gate_status=ready`，5 张图的 sha256/字节与 manifest 逐条相等。
- 回放脚本：`b19_refresh.py` / `b19_finish.py` / `b19_adopt2.py` / `b19_deliver.py` / `b19_export_project.py` /
  `b19_roundtrip.py`（同一隔离 profile 跨进程复用，origin 固定 `http://127.0.0.1:5512`；导入复验用
  `b16_import_host.py` 的拒绝型 provider，`5507`，零外呼）。
- 两包往返：`b19-project-post-suite.zip`（39,555,718B，340 文档/28 资产）导入全新 origin 后
  **文档 kind|id|version 集合、payload、资产 sha 全部相等**（340/340、28/28，资产 digest 自洽），
  刷新后不变；再导出 369 个成员中只有 `manifest.json.exported_at` 不同（其余逐成员字节相等）。
- 未做：新像素的人审、PR#21 合并/部署、批次18线上五图与同源恢复（线上仍是 `689c6b08` 发布）。

## 未证

- 未验证生成后的像素是否合格；确定性门与形状核对不等于人审。
