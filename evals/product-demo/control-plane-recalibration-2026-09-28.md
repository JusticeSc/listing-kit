# 2026-09-28 控制面重建审计

> NOT-AUTHORITY · point-in-time evidence  
> 本文件只记录本次校准发生了什么；产品目标只读 `docs/product-demo-goal-and-implementation-plan.md`，执行状态只读 `_working/amz-listing-kit-product-demo/state.md`。

## 1. 触发原因

系统 Goal 与 v1.22 计划仍以 Aster 01、F1–F8 和“先做因果 Mock 产品”为主线，但产品方向已经明确改变：

- 产品必须接受新商品输入，而不是围绕固定杯子夹具；
- 工作空间采用文件夹形态并持久保存完整过程；
- ProductBrief、动态 Plan 和 Prompt 由语义模型按输入生成；
- 图片生成默认真实调用 qwen-image-3.0，但通过 Provider 接口解耦；
- 不再用模型能力实验决定是否建设产品；
- 先交付真实可用纵向切片，Mock 只服务错误和恢复测试。

如果继续沿用旧 Goal，后续即使把第三版原型实现完整，也只能得到“夹具驱动的演示控制台”，不能得到任意商品工作台。

## 2. 审计结论

| 事实类别 | 校准前 | 校准后 |
|---|---|---|
| 产品目标权威 | 同一路径 v1.22，正文积累 17 次补丁并保留旧 Aster objective | 同一路径 v2.0，重写为商品工作空间、动态编译、真实生成、返工与导出 |
| 执行状态权威 | Phase 2 blocked，下一任务 D2.R1g | Phase -1 blocked，下一任务 D-1.2：替换并绑定系统 Goal |
| 当前实现权威 | README 把旧 Mock 与多个历史入口并列描述 | README 继续只描述现有实现，并明确正式 Product V1 尚未施工 |
| 历史证据 | 旧计划与 state 会被覆盖 | 覆盖前复制到 `_stage-amz-control/product-v2-plan-20260928/` |
| Skill 参考方式 | 借用了若干界面和术语，但正式编译器仍是 fixture lookup | 明确组合 Workspace/Product JSON、Prompt Grammar、Provider/manifest 三类机制 |

## 3. 旧工作如何处置

- `demo/provider/dashscope_i2i.py`、front-chain 合同、Unknown/幂等探针：保留为正式 Provider 的迁移输入；
- `app/server.py`、旧 Mock service：保留入口与异常轨迹工程资产，业务 fixture 逻辑不复用；
- `evals/product-demo/d2-r1g/`：保留阶段式 UI、布局和负样本证据，不把 `FIX.aster/FIX.bex` 当正式 ProductCompiler；
- v2 文件/导出/版本经验：按消费方选择性迁移；
- D2.R1b–D2.R1i 旧任务图：由旧计划快照解释，不进入新 current state；不改写为完成。

## 4. 关键设计裁定

1. 文件夹 Workspace 是业务权威；V1 不同时引入 SQLite 业务状态，避免双状态源。
2. SemanticProvider 动态生成 ProductBrief、PlanDraft 和 PromptBlocks；确定性代码校验并编译最终 Prompt。
3. Shot Archetype 是通用任务语法，不是固定套图配方；Plan 数量为 `1..N`。
4. ImageProvider 管理真实生成和外部任务身份；业务状态机不绑定 qwen-image 专属字段。
5. 用户拥有最终采用权；V1 自动检查只裁决文件和平台硬规则，语义/审美验证器推迟。
6. 模型选择器推迟，但 Provider registry 和 model 字段从第一版存在。

## 5. Goal 不一致与开工门禁

读取系统 Goal 的新鲜结果为 `paused`，objective 仍是 Aster 01 完整演示目标。它与 v2.0 §2 不一致，因此：

- current state 保持 `paused`；
- Phase -1 标记 `blocked`；
- 唯一下一任务为 `D-1.2`；
- 不进入 Phase 0，不修改产品代码，不产生付费模型调用；
- 用户在应用中替换/重建 Goal 后，重新读取 Goal 并更新绑定，再执行 D-1.3。

## 6. 文件快照与哈希

快照目录：`_stage-amz-control/product-v2-plan-20260928/`

| 文件 | 校准前 SHA-256 |
|---|---|
| `docs/product-demo-goal-and-implementation-plan.md` | `6418B537315095AA0D159B30B0E05BC6EBE94017AD9169758F46907FE9B87D39` |
| `_working/amz-listing-kit-product-demo/state.md` | `F2B90E074C880F1E51736BBF6BFF40015DC36FB3A7AF8F623F2E258503C98C44` |
| `docs/INDEX.md` | `C38C5EA252BC76BAF808324EC0063747A70695A4ACD0A6B0A1D364A0091708CA` |
| `README.md` | `BAF35865697CEF8612FFF3791D312C9EC5281004B46CBF53D3FB347EECB4E167` |

v2.0 产品计划写入后 SHA-256：`538EA4DC1DFE5704A8470A94072FCF25876BF0D5B1346D9621732AD79C91406F`。

## 7. 验证结果

同步完成后于 2026-09-28T12:10:17+08:00 执行：

| 检查 | 结果 | 能证明什么 |
|---|---|---|
| `tools/check_project_state.py` | 退出码 0，J0–J10 全过 | 六阶段、29 个任务、依赖、证据、暂停状态和唯一下一任务一致 |
| `tools/check_docs.py --no-run` | 退出码 0 | 31 份受管文档双向登记一致；产品目标/执行状态/实现各一份权威 |
| `tools/check_docs.py` | 退出码 0；真跑 11 条去重命令，34 条按规则跳过，1 条付费命令被改为 dry-run | 文档命令和当前实现约束没有因控制面修改而失配；未产生付费调用 |
| 计划结构读取 | v2.0；Phase `-1,0,1,2,3,4`；Gate `G-1,G0..G4`；任务 29 条 | 计划和 state 可由守卫机械关联 |

校准后文件 SHA-256：

| 文件 | 校准后 SHA-256 |
|---|---|
| `docs/product-demo-goal-and-implementation-plan.md` | `538EA4DC1DFE5704A8470A94072FCF25876BF0D5B1346D9621732AD79C91406F` |
| `_working/amz-listing-kit-product-demo/state.md` | `6BF8CC4AD62578C40E4F9A4DCE4D707A35F28B53903279C46F62BFB08378E471` |
| `docs/INDEX.md` | `422D862151B23440F66EF5E73A727A5835E0181DD0541E39C6BFB10FDD5B96A0` |
| `README.md` | `5A64CE66DA578831C3CB2C372947B94CD444CF200EA6B6D11192DB0758A1D314` |

结论：文档控制面已校准并通过现有守卫；系统 Goal objective 仍未替换，所以项目诚实地停在 `D-1.2`，不能据此声称正式开发已开始。
