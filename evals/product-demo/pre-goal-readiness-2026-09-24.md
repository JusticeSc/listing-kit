# 正式 Goal 前准备审计

时间：2026-09-24T11:56:32+08:00  
对象：`amz-listing-kit` 完整演示产品  
结论：**可代办准备已完成；等待项目发起人正式恢复系统 Goal。**

本审计只回答“恢复 Goal 后能否从 Phase 0 有控制地开工”。它不证明参考资产已经生成、图生图已经实现、图片已经可用或完整产品已经完成。

| 准备条件 | 当前证据 | 结果 | 边界 |
|---|---|---|---|
| Goal 文本与计划一致 | 系统 Goal `01a0ca17-2179-7eb0-969a-af9c79c4d8ca` 当前 objective 与计划 §2 一致 | ready | 系统状态仍为 `paused`，尚未获得正式开工信号 |
| 目标与执行权威唯一 | `docs/INDEX.md`；`tools/check_docs.py` | ready | 旧计划、旧需求记录只保留为历史证据 |
| 执行状态绑定真实 Goal | `_working/amz-listing-kit-product-demo/state.md` | ready | working state 是续作记录，不替代系统 Goal 状态 |
| 当前工程基线可定位 | `evals/v2_baseline_manifest.json`；代码树 `content-tree-sha256=c368f04ff4fc2235…` | ready | 冻结的是旧 v2 工程起点，不是新产品验收 |
| 当前完整回归无既有红项 | `evals/last_regress.txt`：21 通过、0 环境拦下、0 未通过 | ready | 证明既有判据当前通过，不证明新 Goal 功能 |
| 基线可复核 | `tools/snapshot_v2_baseline.py --check` 当前通过 | ready | 项目不是 Git 仓库，使用内容树哈希代替 commit id |
| 百炼凭据具备且未落项目文件 | 进程环境 `DASHSCOPE_API_KEY=PRESENT`；项目根 `.env=ABSENT` | ready | 未显示、未复制、未验证额度；真实调用在 Phase 1 受控执行 |
| 默认模型明确 | 环境未覆盖 `IMAGE_MODEL`；`src/imagegen.py` 默认 `qwen-image-3.0` | ready | 运行时仍必须把实际 model、参数和响应写入证据 |
| 官方 I2I 契约已核对 | 阿里云百炼 3.0 API：支持 1–3 张参考图；DashScope I2I 在 `messages[].content` 中按序放 `image` 与 `text`；异步任务可用现有 image-generation endpoint | ready | 模型、Endpoint 与 API Key 必须同地域；正式适配在 D1.1–D1.3 实现与验证 |
| 当前最早能力断点已定位 | `src/imagegen.py` 的 `generate_image()` 无参考图参数，`_build_body()` 只发送 `text` | ready-to-change | 当前代码不能作为 I2I 已实现证据 |
| 数据外发边界已决定 | 计划 §2–§3：参考图进入百炼是正式能力固定前提，无纯文生图/本地贴图伪等价路线 | ready | 产品仍需清楚告知参考图将发送给百炼 |
| 首个付费实验预算与停止线明确 | 计划 Phase 1：首轮 4 张，最多一次受控复验，总计不超过 8 张；失败即停 | ready | Goal 恢复前不调用模型、不生成正式参考资产 |
| Aster 01 夹具合同明确 | 需求分析 §17、计划 Phase 0 / D0.1–D0.4 | ready-to-build | 参考板和三张单视图尚未生成，这是 Goal 恢复后的首个实施阶段 |

## 当前唯一外部动作

项目发起人在 Goal 控件中把 `01a0ca17-2179-7eb0-969a-af9c79c4d8ca` 从 `paused` 正式恢复。恢复后必须重新读取 Goal 状态；只有仍为同一 objective 且状态为 `active`，才允许补齐 Gate G-1 并开始 D0.1。

## 官方能力来源

- 阿里云百炼《千问-图像生成与编辑3.0 API参考》：https://help.aliyun.com/zh/model-studio/qwen-image-generation-and-editing-api-reference

