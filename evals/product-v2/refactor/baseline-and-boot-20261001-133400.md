NOT-AUTHORITY: point-in-time evidence; not a plan, current state, or product completion

# V2.R1.2 可达基线增补 · 20261001-133400Z

## 1. 本卡回答什么

R1.2 卡（计划 §9 V2.R1.2）要求：记录两处已修 UI 问题与后续 boot 失败的时间/条件/证明范围；
核查已有轨迹缺口和 readiness 窗口；设计可控延迟/失败注入，不为确认失败而重复运行；
保存旧包和含历史候选代表项目并核对 hash 与版本。调查完成不等于缺陷修复，发布阻断语义留给 R3.3/G3。
本增补只做 R1.2 范围内“此前缺失、现在可达”的三件事；root cause 仍保持未知，不闭合缺陷。

前序基线（095710Z）已覆盖：两处 UI 修复的脏树核对、061430 失败样本与 0633 双绿的 git 内复现、
9 文件回退 hash、迁移链现状、可控延迟设计（未执行）。
前序审计（103825Z A1/A2/A4）指出本卡此前缺口：
A1 包层缺旧格式包与多候选历史代表项目；A2 离线 harness 只注语义 fake；
A4 启动时序描述错误（解锁在 openStorage 前，不在后）。

## 2. A2 关闭：四 fake 离线隔离（真实执行，已验证）

### 2.1 缺口复现（执行前，先证明缺口真实存在）

旧 `tools/v2_test_server.py:47` 只注入 `server.provider_factory = FakeSemanticProvider(ok)`；
`app/product_v2_server.py:196-209` 其余三类回落 `default_*_factory` → 注册表默认 dashscope-*。
本机实测（环境残留 `DASHSCOPE_API_KEY`，`uv run` 同进程内 `create_product_v2_server`
仅注语义 fake，GET /api/v2/capabilities）：

- semantic = `fake-semantic`；images.provider = `dashscope-qwen-image` configured=true；
- review.provider = `dashscope-review` configured=true（含 endpoint_host/transport 明细）；
- suite.provider = `dashscope-suite-review` configured=true。
- 即：在“审计者自以为离线”的 harness 上，图像/复核三路仍是真实 Adapter 身份。
- 未发起真实生图/复核请求（只读 capabilities，未 POST 提交），不宣称产生过付费。

### 2.2 修复（只改测试 harness，不改产品代码）

`tools/v2_test_server.py`（diff 未提交，见 §6 hash）：四个 factory 全部显式 fake
（fake-semantic / fake-qwen-image / fake-review / fake-suite-review），注释写明回落原因。
`verify_v2_1_2/verify_v2_1_3/verify_v2_ui_1_remote_entry` 经 `start_server()` 自动继承；
其余 `verify_v2_*` 本就经 `create_product_v2_server` 显式注入四 fake（grep 见 §4），行为不变。

### 2.3 修复后验证（真实执行）

- 同进程 capabilities：semantic/images/review/suite 四路 provider_id 依次为
  `fake-semantic` / `fake-qwen-image` / `fake-review` / `fake-suite-review`。
- 四类网关链（同进程 POST，显式构造 body 按各契约）：
  semantic analyze ok（proposal slots 含 product_name=R12）；
  images submit → task `fake-342e67e1a36d29c1` → status SUCCEEDED → result 179 字节 PNG 头；
  review/candidate ok（contract v2.5.2，findings deformity 样例）；
  review/suite ok（contract v2.5.5，checked 1 张，无跨图发现）。
  途中两次 body 形状错误均为调用方参数错误（submit 引用了未按 task 派生的字节；
  result 路由回原始 PNG 字节；review/suite 初版字段名与契约不符），按验证器既有
  `review_payload` 形状纠正后通过；不涉及产品代码修改。
- `verify_v2_1_2_project_home.py --label r12-fourfake`（修复后 harness 上实跑）：
  11/11 全过，证据 `evals/product-v2/v2.1.2-project-home-20261001-212935-r12-fourfake.{txt,json}`。
- 结论：A2 在 harness 层关闭。后继离线审计必须经此四 fake harness（或等价显式四注），
  不依赖默认回落。本增补不证明“无凭据时的拒绝语义”，那是各验证器既有判据的范围。

## 3. 可控延迟/失败注入（真实执行，判据只到 R1.2，不闭合 R3.3）

沿用 095710Z §5 指定的现成缝（`_resolve_static` 包装 + `BOOT_TRAIL_SCRIPT` init script），
本轮真实执行两组（均为临时脚本，未落盘产品/验证器修改；trail 判读规则沿用验证器既有注释）：

### 3.1 延迟 app.js 2500ms（首屏模块迟到）

- 手段：`_resolve_static` 内 `time.sleep(2.5)`（仅 app.js），trail 用 `add_init_script` 文件注入，
  快照用页面内联求值（快照箭头经 `evaluate(arg)` 传递会触发正则解析错误，改内联）。
- 结果：`ready_ms=2585`（等待 `#create-project` enabled，timeout=30s 内通过）；
  trail = `[observing loading@12, attr null→true@2559, attr ""→false@2563]`；
  终态 view_hidden=true / empty_hidden=false / rows=0 / page_errors=[]。
- 判读：trail 完整捕获 disabled true→false 窗口，与“模块迟到但 boot 照常完成”一致；
  ready 语义仍是“控件解锁”（openStorage 后 refresh 前），不是 boot 完成——
  纠正 095710Z §3 表格旧描述（A4 已指出，解锁在 `app.js:502`，openStorage 在 505）。
  本组不复现 061430（当时无 trail、无资源耗时、无模块加载证据），只证明延迟探针有效。

### 3.2 workspace.js 404（模块加载失败）

- 手段：`_resolve_static` 对 workspace.js 返回 None（404），观察 4s。
- 结果：trail 只有 `[observing loading@12]`（无 attr、无 view-shown、无 err/reject）；
  create_disabled=false（HTML 默认无 disabled，boot 第一行未执行）；
  console 有 404 资源错误，pageerror 无，boot-error 为空，view 保持 hidden。
- 判读：符合验证器既有规则“只有 observing + has_disabled 恒 false ⇒ boot 未执行
  （模块没加载或没跑到第一行）”。同时暴露判据缺口：模块 404 时 boot-error 为空、
  控件保持可用态（不是禁用态），用户看到的是“空白首页、点新建无响应”，
  不是明确失败——该缺口归 R3.3（显式 ready/失败语义），本卡只记录。

### 3.3 与 061430 的关系（明确不闭合）

061430 样本（`9dc6559`）失败点是旧判据 5s 可见性超时、无 trail、无资源耗时；
本轮两组注入都有 trail 且行为可解释，但注入的是“已知延迟/已知 404”，不是 061430 的
“满载首轮未知卡点”。Root cause 保持未知；R3.3/G3 门保持；后续调查判据沿用 095710Z §5：
延迟 Xms 下 trail 定位最早失效层、旧回调不串写、双标签冲突可见、≥2 轮 trail 一致。

## 4. 包层基线（真实执行：新往返证据 + 旧缺口精确定位）

### 4.1 本轮新证据（全部当日新鲜，非 git 内旧样本）

- `verify_v2_1_3_project_package.py --label r12-baseline`：8/8 全过
  （`evals/product-v2/v2.1.3-project-package-20261001-212812-r12-baseline.{txt,json}`）：
  导出包标准 ZIP（bad_crc=null，format=amz-listing-kit-project version=2），
  2 文档 + 2 资产逐项哈希一致，清空后导入 `documents_equal/assets_equal=true`，
  重复导入新 project_id 且各 2 文档/共 4 资产，损坏包拒绝且项目数不变，全程零 console/page error。
- `verify_v2_6_3_project_transfer.py --label r12-baseline`：13/13 全过
  （`evals/product-v2/v2.6.3-transfer-20261001-213507-r12-baseline.{txt,json}` + 7 张 evidence 截图）：
  A 导出格式 2（50 文档含 candidate/export_record/fact_slot/attempt/confirm/prompt/review/selection/
  suite_plan/suite_review 等 11 种 + product_input，5 资产，自描述 true，integrity 50/5/78190/33039）；
  B 全新 profile 导入逐文档 payload 哈希与资产 sha256 一致（missing/changed=[]）；
  B 返工 candidate 4→5、attempts=15；返工后门禁就绪并生成交付包
  （`V263-迁移品-交付包-20261001-1335.zip` 48658 字节）；
  B 再导出 A 记录逐条保留（50→60 文档，新增 10 条含返工/交付 8 种）；
  格式 1 旧包（由 A 包降级合成）导入提示升级且冲突分配新项目；
  双浏览器零 console/page/HTTP 错误；正式入口自检 38/38。
- 以上是“当前代码 + 合成业务链”的往返基线：证明导出/导入/迁移/返工/交付链路可重复，
  不证明“旧真实包可恢复”（见 4.2）。

### 4.2 旧缺口精确定位（仍未关闭，阻止 R1.2 done）

- `rehearsal-exports/` 17 个交付包 + `real-e2e-091400/delivery-091400.zip` 经实测：
  以 `20261001-095045-v2614-reg-V273-夹式-LED-阅读灯-交付包-20261001-0150.zip` 为例，
  7 条目（README/checks/manifest/4 图），`testzip` 通过，但 manifest 是交付清单
  （contract_version/images/inputs_fingerprint/selection_fingerprint），
  不是项目包 manifest（无 format/documents/assets/integrity），不能替代完整项目历史包。
- 103825Z A1 所指临时完整项目包（74 文档/5 资产/4 候选/16 attempt/4 选择，
  sha `a98e2b0b…`）本轮未重读（目录已不可达）；其“每 Shot 仅一候选”本就不足以替代
  多候选/返工代表项目；format-1 真实旧包仍未选定（本轮 format-1 仅为 A 包降级合成）。
- 本轮把当日 V2.6.3 双浏览器链路的真实产物保存为可恢复包基线（`evals/product-v2/refactor/packages/`，
  保存时刻 20261001-134836Z，逐包 `testzip` 全过、记录自描述与资产哈希已独立复核；
  来源为本机 `%TEMP%/amz-v263-u7bo0psn/downloads/` 同轮产物，与
  `v2.6.3-transfer-20261001-213507-r12-baseline.json` walkthrough B 包 174667 字节一致）：
  - `r12-baseline-project-a-format2-50docs.zip`：130362 字节，
    sha256 `d8421b567d9499cee7adfc5d1042bd2e6bcb557891f513441ab0722320a4a52d`，
    格式 2 / 50 文档 / 5 资产（4 候选分属 4 Shot + 12 attempt + 4 选择 + 4 复核 + 交付前状态）。
  - `r12-baseline-project-b-history-60docs.zip`：174667 字节，
    sha256 `09ed48fea444ba241211763092b3a8df169f707800e12fea89f46608e2b13fc0`，
    格式 2 / 60 文档 / 6 资产（含 shot_main_clean v1+v2 双候选、返工后 15 attempt、
    5 选择、返工/交付新增 10 条 8 种）；B 再导出时 A 的 50 条逐 payload 哈希原样保留
    （V2.6.3-08 kept=true），即含历史候选的代表项目。
  - `r12-baseline-project-a-format1-50docs.zip`：39438 字节，
    sha256 `2036c5e003e919cd7330ab08233a317016ddac961ff7130e249bed0710d60a68`，
    格式 1 / 50 文档 / 5 资产（由 A 包降级合成，V2.6.3-09 已验证 UI 导入升级路径）。
  以上是合成业务链产物，可作“形状代表”与回退对照，不是真实历史工件；真实旧包仍缺。

## 5. A4 时序纠正确认

`app/product_v2/app.js:499-526` 实测代码：`probeBrowserCapabilities()` → 502
`setHomeControlsBlocked(blocked)` → 505 `openStorage()` → pointer/refresh → workspace.open。
解锁早于 openStorage（103825Z A4 正确，095710Z §3 表格“解锁在 openStorage 后”作废）。
boot 重入（`void boot()`）、`workspace.close()` 未 await、`db.js onblocked` 空实现、
无 BroadcastChannel 仍是现状（本轮只读核对，未改产品代码）。

## 6. 回退基线（hash，含本轮唯一产品外修改）

记录时刻 2026-10-01T13:34:00Z；HEAD=`ed363d3`（与 095710Z 同）。
095710Z 表中 9 文件本轮重算全部一致（workspace.js `9101172b…`、package.js `b0722141…`、
package-migrations.js `073d069e…`、transfer.js `02b6cbdd…`、repository.js `c18f3095…`、
db.js `e9499bcb…`、verify_v2_1_2 `01e04faf…`、verify_v2_2_3 `b9af31e1…`、
verify_v2_1_3 `22005e1d…`），即产品代码与旧验证器自 095710Z 无字节变化。
唯一变化是本轮 R1.2 范围内的 harness 隔离修复：

| 路径 | sha256（工作树） | 说明 |
|---|---|---|
| `tools/v2_test_server.py` | `2ea8179654e61ec33757aad213580e2265dd7e0ed531bacb588e6171eb973ccf` | 四 fake 显式注入（旧值见 git diff） |

回退 = `git diff -- tools/v2_test_server.py` 核对后 `git checkout -- tools/v2_test_server.py`
（仅此一处产品外修改；其余 14M 脏树与 095710Z 清单同范围，state 指针更新除外）。
`git diff --stat` 本轮：15 files +859/-1097（含 state 大幅精简，那是 R1.1 绑定后的权威形状，
非本卡修改）。

## 7. 验收对照（诚实范围）

- A2 harness 隔离：已执行四 fake 修复 + capabilities/四链/V2.1.2 全绿 → 本增补 proven。
- 可控延迟/失败注入：延迟 2.5s 与 404 两组真实执行、trail 可判读 → 方法 proven；
  但复现的是已知注入，不是 061430 根因 → 缺陷仍开放，R3.3/G3 门保持。
- 包层：当日新往返（V2.1.3 8/8 + V2.6.3 13/13）proven；旧真实包/多候选历史工件 missing →
  R1.2 整体仍 pending，blocker 保持，不伪造 done。
- 产品代码：本轮零修改（9 文件 hash 全等）；唯一修改是测试 harness 隔离，
  无消费者行为变化，无需回归除已跑的 V2.1.2/V2.1.3/V2.6.3。
- 未触达：真实模型、第二模型、BYOK、默认档、C17/C15、V1 日落、部署、Git 提交/推送。
  本轮新增证据（四 fake 链探针除外，均为验证器落盘文件）未提交。
