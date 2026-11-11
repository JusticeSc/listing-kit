<!-- 拆分件 03/03 · 父文档 evals/product-v2/refactor/packet11-convergence-20261008.md -->
# 6. 后续规划（按计划依赖顺序，判据与授权边界）
[返回 packet11-convergence-20261008.md](packet11-convergence-20261008.md)

## 6. 后续规划（按计划依赖顺序，判据与授权边界）

1. **G6/R7.5 类型覆盖**：`app`/`workspace`/`session` 等剩余 Module 按批 TS 化，调用方同批改道；
   `check:types`/`check:generated` 必须覆盖全部迁移 TS 及其浏览器 JS。判据：同一批内
   新建 + 改道 + 删除旧实现在一个验收单位内，任何提交点不得存在两份活着的同一逻辑。
2. **消费者切换与当前格式数据恢复**：G6 成立后按 §15.6.2 逐项核对可复用资产与受影响前提。
3. **R7.3 V1 工程清理**：按实际消费者闭包删除 V1 活路径/失效依赖，保留共享依赖与历史原件。
4. **R7.1 最终两轮**：删后跑完整两轮、指纹一致；计一个验收批次（当前已用 0/10）。
5. **真实能力补证（授权内）**：RC09 两个真实图像模型 + 一次真实图文/复核，最多 5 次生图
   （每次 1 张）与 2 次理解/复核、增量 ≤3 元；先预留、失败也计次、Unknown 不自动重提。
6. **R7.4 收口**：`refactor/completion-matrix-<ts>.md/json` 逐行适用项、无 missing/indirect/contradicted；
   PR 满足现有 CI/审查/分支保护后由代理合并并发布，发布后核对 HTTPS/静态/页面主链与最终指纹。

许可边界不变：C15/C17 需要真人到场（不适用项按 RC18 记录，模拟 E2E 不冒充）；
付费/上传/提交/部署/日落各自设门。

## 7. 明确未成立 / 未做（不得声称）

- C15/C17 独立真人走查未发生；模拟 E2E 不替代。
- 真实 Docker/TLS/HTTPS 发布、回退轨迹与同 origin 数据恢复：本机无 Docker 守护进程，未执行发布。
- V1 清理、删后两轮、最终完成矩阵、真实模型补证：未执行。
- RC19（Windows 回环间歇）**根因仍未定**：本轮只是把一类症状（死端口被代理伪装成 502）从
  诊断链上移除，并对 harness 页载入卡住加了传输签名重试 + 留痕；不得据此声称间歇已根治。
- 本机没有 docker daemon：Docker 构建/烟测、镜像 origin 页面、真实回退与可信 HTTPS/同 origin 数据恢复
  **一律由远程 CD（GitHub Actions）证明**（用户指令：不用本机 docker）；本报告与 §9 只声明已运行的远程判据。
- 付费模型调用：本轮 **0 次**（未部署亦未付费）。提交/推送/PR 见 §9。

## 8. 恢复点与文件

- 进度权威：`_working/amz-listing-kit-product-v2/state.md`（已写入本轮条目；仍 V2.R5.1）。
- 冷恢复：`uv run --locked python tools/refactor_resume.py`。
- 本报告：`evals/product-v2/refactor/packet11-convergence-20261008.md`。
- 本轮定稿的产品改动：`app/product_v2/workspace.js`（设置订阅只落盘草稿、不在能力就绪前派生）。
- 本轮定稿的验证侧改动：`tools/v2_verify_shared.py`（回环 no_proxy + `read_suite` 诊断/传输签名重试）、
  `tools/verify_v2_ui_2_interaction_visual.py`（`STORAGE_DUMP`/`storage_diff`/`WRITE_TRACE` 与 UI2-17 留痕）、
  `tools/verify_v2_4_2_generation_attempt.py`（同端口重启 + `-20` 原始载荷证据）、
  `tools/verify_v2_1_4_formal_entry.py`、`tools/verify_v2_2_3_intake_understanding.py`、
  `tools/verify_v2_5_2_vlm_review.py`、`tools/verify_v2_6_1_selection.py`（悬挂引用）。
- 工作树里同批但更早定稿的改动（同批已提交，本轮已复跑验证）：3_5/4_4/5_3/8设置验证器、
  `generation.ts/.js` 与 `ui/generation-view.ts/.js`、`app/product_v2_server.py`、
  `tools/release_transaction_probe.py`、`.github/workflows/ci-cd.yml`（源码钉→行为证据）、
  `docs/`、`AGENTS.md`、`README.md`。
- 一次性探针（本地，忽略入库）：`_working/p11fix/_probe_*.py`；同套件重复判定的中途证据在
  `_working/p11fix/scratch/`。

## 9. 提交、远程 CD 与首次 CI 判红（2026-10-08）

用户指令：**不用本机 docker，容器与发布单位由 CD 的远程服务证明**（本机也无 docker daemon）。

- 提交（`feat/v2-r51-packet-05` → `origin`，draft PR #4 → `main`，**未合并**）：
  `6b37145` 入口按 HTTP/1.1 复用连接并容忍客户端中止；`8d0320d` 设置草稿/候选配额受阻/取回按钮；
  `22db254` 验证器与 CI（`--offline-rollback` 行为证据、packet08 三件套进 CI）；
  `179e8da` 守卫 J6 未入库证据告警；`8c35e64` 控制面与证据、两个事前快照。
- 触发面：`.github/workflows/ci-cd.yml` 只在 `main` push 与 **PR→main** 上运行；本分支此前无 CI 门
  （`db0ec47` 已记录），本轮开 PR 才第一次拿到远程判据。
- 首次运行 `37712743152`（head `22db254`）在「Check control plane」判红 **13 条 J6**：state 里
  V2.R4.3/V2.R4.4 的 evidence 指向 `evals/product-v2/*.txt|*.json` 运行日志——这些路径被 `.gitignore`
  默认拦住，本地工作树里存在、干净检出后不存在。**属控制面缺陷（证据指针指向不可能入库的路径），
  不是产品缺陷。** 修复：13 份按仓库既有约定 `git add -f` 晋级；`tools/check_project_state.py`
  的 `_evidence_ok` 复用已有 `_tracked`，对「存在但未入库」发 `[J6-warn]`（不判失败——pre-commit 阶段
  通常还没 add）。实测：临时撤出 1 份 → 警告出现且 rc=0；重新 add → 警告消失。
- 快照入库的字节事实：整树快照自带 `.gitattributes`，更靠下的规则优先 → 其文本文件仍按仓库行尾政策
  入库。实测 423 份中 **366 份逐字节一致**，57 份**只差 CRLF→LF**（每份字节差 == 其 CRLF 行数；抽样
  `.dockerignore` 28/28、`Dockerfile` 40/40、`generation.ts` 1524/1524、state.md 440/440），内容不变；
  manifest 哈希按采集机字节校验。新增 `_stage-amz-control/** -text` 让不带嵌套属性的快照按原字节入库。
- 交由远程 CD 证明（本机不做，也不以静态核对冒充）：Docker 构建与烟测、
  `tools/release_transaction_probe.py --selftest`、被测镜像 origin 的页面、真实不同版本服务回退、
  可信 HTTPS/静态资源/隔离页面主链与同 origin 数据恢复。
