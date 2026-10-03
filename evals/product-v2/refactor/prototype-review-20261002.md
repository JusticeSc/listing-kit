NOT-AUTHORITY: point-in-time V2.R2.2 prototype evidence; not a product implementation, release acceptance, dependency approval, or human walkthrough.

# V2.R2.2 · 可操作原型与交互验收冻结

输入：R2.1 `ui-baseline-20261001-chrome.md`（B01/G01/H01/H02/H03/V01，T7 缺口）＋ UI 合同 V2.UI.2（draft）＋ 不变量（context §6）＋ R2.3 `reference-review-20261001.md`（SEL-019）。
动作：资料确认、图片比较/返工、错误恢复的可操作浏览器原型；同 Shot 图片上下文、比较导航与信息摆放实测；必要确认保留；采纳项写回 UI 合同 §10 并冻结 §7.2 判据。
权限：计划 §3 后台自动化授权——独立临时配置 Chrome 无头（`154.0.8037.93`），四类 fake 上游，真 handler＋真 IndexedDB。不调用真实模型、不付费、不上传、不提交/推送、不部署。原型仅在 `?prototype=workbench` 隔离 launcher 加载，原型不得混入正式默认数据。

## 1. 原型实现（可移除，不碰产品）

| 文件 | sha256（前 16 位） | 说明 |
|---|---|---|
| `evals/product-v2/harness/workbench-prototype.js` | `aaa2dff6e0557b87` | 布局重组＋原生 dialog＋事实影响＋Unknown 分层＋焦点返回，全 174 行 |
| `evals/product-v2/harness/workbench-prototype.css` | `2c0ebc13794d5bef` | 仅原型样式，token 沿用产品 `styles.css` |
| `evals/product-v2/refactor/_prototype_smoke.py` | throwaway | 隔离无头验证脚本，跑完即证据，不进产品 |

工作树既有脏改（`app/product_v2/workspace.js` 等 M）为此前遗留，非本轮引入；本轮未改 domain/repository/产品 UI。原型行为：

1. 同 Shot 图片工作区：比较面板移入审核卡之后，参考/旧/新候选并排（`#prototype-image-plane`），返工/采用面板移入同一任务上下文，不再需要记忆另一屏。
2. 原生 `<dialog>` 包裹返工/采用面板：打开时把当前 Shot 的参考与候选克隆进对话框上下文，图片上下文不丢失；取消/关闭一律走产品原有 cancel handler（`rework-cancel`/`adopt-cancel`），不产生业务选择或提交。
3. 资料确认影响条：事实编辑后显示失效发送摘要名单（stale rows 名单＋“重新编译并人工确认后才能生成；已有候选与人工采用记录保留”），一键定位到生成阶段；不自动提交。
4. Unknown 分身份恢复：已知 task（有“核对任务”按钮）与无 task 显示不同解释，技术身份/错误收进 `<details>`，秘密不回显（本轮全 fake，无秘密）。
5. 焦点返回：返工/采用/比较关闭后焦点回到触发器；Escape 在 dialog 内转取消、在比较区转收起。

## 2. 无头验证：PASS（`prototype-smoke-20261002.json`，`ed417438…`）

`result PASS`，`finished_at 2026-10-01T17:27:15.983323+00:00`；`console_page_errors []`，`blocked_requests []`（loopback 外请求零放行），100 条请求全为本地静态与 capabilities。

| 场景 | 证据 |
|---|---|
| 单图返工隔离 | `shot_infographic_benefits` 返工后 1→2 候选；无关 Shot 记录相等、selection 记录相等 |
| 无 task Unknown | 无“核对任务”按钮，保留旧候选 1 个，不伪造查询 |
| 已知 task Unknown 核对 | 状态仍 unknown，submit 数 3→3，无重复提交 |
| 原生 modal Tab 包络＋Escape | 16 步 Tab 始终在 modal 内且焦点轮廓可见，Escape 回到 `rework-open`，比较区保留 |
| 事实编辑影响＋继续 | 4 张 Prompt 变 stale，影响条文本精确，候选/采用保留，submit 数不变，一键进生成阶段 |
| 刷新 | 记录逐字节相等，submit 数不变，快照 sha256 `a8055157…` |
| 响应式 9 面 | 1440/1366/390 × 理解/比较/生成，`scrollWidth ≤ width`，无 CSS zoom/transform 冒充 |
| 真 zoom 12 面 | 1440/1366 × 125%/200%（Chrome 设置页真实 zoom，非 CSS），`innerWidth ≈ w/z`，DPR 1.25/2，`visualViewport.scale=1` |
| 截图 4 张 | `prototype-compare-1440/-390/-native200`、`prototype-facts-1440` |

轨迹说明：smoke 自身 `trail` 为 reload 后读数＝0（预期，reload 后新页数组为空）；reload 前 27 次 click 完整轨迹在 `prototype-observations-20261002.json`（比较→返工→预览→提交→采用→取消→核对链），无多余业务点击——原型复用既有按钮，对话框新增的“预览/确认”属于 R2.2 要求保留的必要确认，不计入可删点击。

失败考古（均保留为证据，不删）：`prototype-keyboard-first-failure`（首版断言要求每步 `document.hasFocus`，撞上原生 Tab 末控件进 browser chrome 的真实行为）→ `prototype-native-focus-diagnosis`（8 步对照：BODY 失焦步 dialog 仍 `open+modal`，非后台化、非 dialog 重建）→ `prototype-settings-context-failure`（`chrome://settings` 在隔离上下文不可导航，Playwright 明确报错）→ 终版改用 persistent context 真 zoom＋Shift+Tab 恢复＋容忍 BODY 失焦步后 PASS。冻结结论：原生 dialog 的 Tab 包络判据是“仍在 modal 内＋焦点轮廓可见”，不以“每步都有 document.hasFocus”判定。

## 3. 问题→设计→冻结判据（对应 UI 合同 §10）

| 问题 | 原型设计 | 冻结判据（可测） | 落点 |
|---|---|---|---|
| H02 图片上下文/滚动 | 同 Shot 参考/旧/新并排工作区，比较入口紧邻任务卡 | 高频比较不依赖记忆另一屏；身份/版本/采用状态文本可辨；比较/采用入口不在整套长卡之后 | R6.2 / RC03 / §7.2 |
| H01 高频继续劳动 | 事实旁原始资料对照＋失效影响条＋重编入口 | 影响范围可见；必要确认保留；成功历史/人工采用不丢；不自动付费提交 | R6.1 / RC14 |
| H03 技术词/异常分支 | 已知/无 task Unknown 分层解释＋details | 已知核对不增 submit；无 task 明确不可查询与重提风险；错误给影响＋下一步 | R5.1 / R6.3 / §7.2 |
| B01 交付溯源错 | 比较区展示候选原 Attempt 身份（原型只读展示，未修产品） | 交付只读采用候选原 action 冻结 Prompt，不读当前编辑头；旧候选 manifest Prompt 与原 Attempt 相等 | R6.3 / RC16 / RC18（仍发布 blocker，本轮未修复） |
| G01 设置能力缺口 | 原型未做设置页（T7 缺口延续） | 设置仅展示可用能力与非 secret 身份；BYOK 内存；默认 key 不送用户目标 | R4.3 / R6.3 / RC08（未冻结，待 R4.1/R4.3） |
| V01 长卡视觉 | 固定比 `object-fit: contain`＋长文本渐进披露 | 测量只证可达/尺寸，不证真实商品对比质量 | R6.2＋真人走查 |
| 键盘/焦点/刷新 | 16 步包络、Escape 回触发器、刷新零重提 | §7.2 基线：焦点可见不被遮挡、关闭回触发器、保存/核对真反馈 | R6 / R7 / RC04（Edge/桌面/真人未覆） |

## 4. 可用商品套图结果：未成立（诚实结论，非证据缺口隐瞒）

当前候选是 fake 纯色测试图（R2.1 V01 已声明）；无真实生图 Adapter（R4.1 未评估、R4.2 未批准、无预算）、无真人验收、B01 未修。因此“得到一套可用商品图片”**无新鲜证据，RC09/RC18 不 proven**。本轮冻结的是验收 rubric（供 R4.2/R6.2/R7.1 使用，概念来源见 §5），不是能力证明：

| 维度 | 通过条件 | 证据形式 |
|---|---|---|
| 保真 | 与参考图一致特征，无结构/颜色/比例改写 | 原图对照人审＋VLM 提示（R6.2） |
| 文字 | 无错字乱码，无未确认文字 | 200% 逐字人核＋VLM 提示（R6.2） |
| 事实 | 卖点/参数与已确认事实一致，无虚构认证/数据/评价；无证据写 placeholder/未知 | 事实溯源（R6.1） |
| 尺寸/格式 | 命中平台规格阈值表 | 像素机检（R6.3） |
| 整套 | 数量齐全、风格 Lock 一致、角度/背景配额、参考身份统一 | manifest＋hash（R6.3） |
| 人审 | C17 签署＋C15 零介入非内置商品全链 | R7.2（self 审/截图/axe 不替代） |

## 5. 电商参考 skill 核查（只读：未安装、未运行、未复制代码/样式/品牌/资产）

三个目录均在工作区根，与 `amz-listing-kit/` 同级；侦察由只读 scout 完成（`MassMeerkat`、`CriticalBovid` 全量报告见 agent 载荷），本节只记录采纳/拒绝结论。

### 5.1 `ecommerce-image-suite-main/`（Apache-2.0，有瑕疵）

1442 行 SKILL＋`scripts/generate.py`（1874 行）＋`analyze.py`＋`check_providers.py`＋`generate_video.py`＋references（平台/图型/供应商/文案/模特）。许可：根 LICENSE 为 Apache-2.0 全文，但 `README.md`/`EXAMPLES.md` 仍写“未附带 LICENSE”（陈旧矛盾），`Copyright [yyyy] [name]` 占位符未填，无 NOTICE，`assets/models/` 45 模特与 `example/` 实拍无来源/许可。结论：**零字节复制，只做概念借鉴**。
关键事实：该 skill **无自动验收**——`generate.py` 只写盘＋`generate_result.json`（`{status, path, name}`），尺寸硬编码（1024/2048、无 `--size`），无 OCR/一致性校验；每条 Prompt 末尾的 `CRITICAL: keep the product EXACTLY the same` 只是 prompt 自述，不是验收结论。
采纳（映射未来任务）：批次 manifest 作验收载体（R6.3）；任务隔离＋单调递增目录（R5/R6）；参考图锁定保整套一致（R6.2）；先单图达标后整套（R5.1）；正/背槽位映射（R6.1 能力投影概念）；保真约束显式化（R5.3 prompt 侧输入，非结论）；不静默重试/Unknown 不重提（R5.1）；凭据脱敏前 6 后 4（R4.3）；作业前能力探测门（R4.3，须走 Adapter 投影）；付费前显式确认（R4.2 需逐项上限）；平台规格表作阈值数据（R6.3）；文案确认驱动（R5.3）。
拒绝：复制代码/Prompt 原文/样式/品牌（通义/豆包/即梦/Seedream/DALL·E 等）/资产/联系方式；硬编码供应商分支（计划明令同协议新增配置不改业务分支）；真实调用/付费；把生成成功当质量通过。

### 5.2 `ecom-details-image-main/`（许可不可依赖）

Skill 包（617 行 SKILL＋25 JSON 模板＋442 行标准库 CLI）。.env.example 注释行硬编码第三方代理 `http://74.48.5.153:3000/v1` 与明文 key（**泄漏样本，永不复用、永不写库**）；根 README 自称 MIT 但**无 LICENSE 文件**；模板参考上游未附许可；`generated-images/`（silk-shirt 13 prompt vs 11 图，缺 2 张无人校验）与 `data/*.jpg`、品牌名（Apple/Hermès/Vogue/Phase One/Kodak/Didot）一律不复用。
验收现状：** prompt 期约束＋人肉 QA**，无 OCR/哈希/规格/齐全性校验——不能当作图片验收系统引用。
采纳：五维判据词表（§4 rubric 来源之一）；hex/占比/留白/字号/配额等可数字化阈值；`proof placeholder` 无证据不虚构；逐图独立 prompt 文件＝溯源单元；Campaign Style Lock 作整套一致性合同概念；缺凭据降级只出计划不调模型；比例×分辨率真值表；“AI 干 0→80、人做 80→100”期望管理；品类风险分级（服装/3C 高翻车，必须参考图）。
拒绝：代码/模板/Lock 原文复制；真实调用＋SaaS 上传产品图；像素/比例双口径混用；把“95% 中文准确率”“一次成型”等经验陈述当保证。

### 5.3 `ecommerce-skills-main/`（MIT 2026 dlazy，26 技能）

实读 `platform-compliance`、`detect-task`、`item-detail` 三 skill＋`shared/scripts/check_listing.py`（383 行）＋`run_loop.mjs`＋`gen.mjs`＋`tests/test_compliance.py`＋`shared/references/platform-specs.md`。
注意阈值与另两 skill 的平台表口径不完全一致（如 Amazon 占比 ≥85% vs ≥70%），采用时以平台最新官方文档为准，各 skill 自述“规则会变”亦如此声明。
- detect-task：主观 VLM 质检——8 固定风险项（商品崩坏/人脸/手部/肢体/文字乱码/光影/边缘融合/平台合规）＋三级风险＋投放/重跑/人工修图＋英文修正句回接 prompt；**全项目固定同一质检 prompt 否则报告不可比**；抽检比（新规范 100%、已验证 10–20%、带人物 30%、纯商品 5%）；承认误报漏报＋人工终审；单张约 3 credits（dlazy 付费，本轮无预算授权，只读概念）。
- item-detail：中文排版四条件（原文「」＋字体字重＋版式关系＋显式不乱码）＋短文案＋分模块＋batch 2–3 挑字＋逐字校对＋不编造功能/认证/促销。
- run_loop.mjs：生成→质检→自动追加修正→重跑（上限 3、默认达标线低风险）→逐轮 manifest（prompt/风险/合规/成本/产物）；合规失败翻成英文约束句回接。
- gen.mjs：统一入口＋`--dry-run` 估价不计费＋`--doctor`＋后端优先级。
- tests：合成夹具（灰底 208 必驳回、留白过多、低分辨率、alpha、比例分平台、`--fix` 后复检必须真过、方图保持、自定义规则覆盖）。
采纳概念：客观/主观分层且**双过才算可投**；固定质检 prompt 保可比；JSON＋退出码进 CI；先检后修再检；合规前置到生成 prompt；抽检策略；逐轮 manifest；dry-run；不伪造测量。
拒绝：复制代码/样式/品牌；新运行依赖（Node 脚本链不在本项目登记内，R3.1 前不引入）；真实调用/付费；样例图资产；把 dlazy 后端数量当成本地能力证明。
三 skill 共同结论：它们提供**流程编排与规格清单**，不提供图片结果验收实现；amz 验收必须自建（§4 rubric＋R6/R7 任务），Skill 产出不是用户行为证明。

## 6. 授权与人审门

本原型**未引入新增高风险含义/授权行为**：返工提交、人工采用沿用产品现有确认；候选导航、打开预览、关闭弹层不产生业务选择或提交。后续任何新增高风险含义另获用户确认。原型 self 审不替代最终 C17/C15（R7.2）；UI 合同保持 draft，C17 确认后才转 current。

## 7. 冻结与未冻结

冻结（强约束，后续偏离需原因证据）：同 Shot 直接对照；采用绑定原 Attempt 冻结身份；Unknown 分身份恢复；事实影响先行、必要确认保留；dialog 焦点包络/Escape 返回；刷新不重提；§4 rubric 维度。
未冻结（不作强约束）：三栏 vs 其他布局；六阶段结构（clean cutover 复访中，合同 §9 末已声明）；具体文案/密度/新增样式；设置页形态（待 R4.3/R6.3）。
清除条件：R6 切片替换原型后删除 harness＋`_prototype_smoke.py`＋失败考古 JSON（保留本报告与 PASS 证据）。

## 8. 未证明与下一步

B01 发布 blocker 延续（R6.3/RC18）；T7 设置能力待 R4.1/R4.3；Edge/桌面专项、真人走查、第二模型/预算、boot 间歇根因待各自任务门。Phase 2 保持 active——G2 闭合递延至设置能力解决或缺口被显式接受为合同修订后；next 指 V2.R4.1（计划 §5 明确允许 G1 后并行模型研究）。
快照（改前）：UI 合同 `a2d26387…`、context `fd1f6bab…`、state `a01ea97d…`，见 `_stage-amz-control/r22-freeze-20261002/`。
本报告 sha256：落盘后由 state 守卫链验证存在性；`latest_audit` 指向本文件。
