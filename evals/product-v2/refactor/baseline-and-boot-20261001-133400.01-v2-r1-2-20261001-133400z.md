<!-- 拆分件 01/02 · 父文档 evals/product-v2/refactor/baseline-and-boot-20261001-133400.md -->
# V2.R1.2 可达基线增补 · 20261001-133400Z
[返回 baseline-and-boot-20261001-133400.md](baseline-and-boot-20261001-133400.md)

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

