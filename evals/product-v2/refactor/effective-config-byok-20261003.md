# V2.R4.3 · 统一有效配置 / BYOK / 出站策略 — 施工时点报告

- CONTROL-STATUS: historical · NOT-AUTHORITY: 本文件是时点证据，不发布当前状态或计划。
- 时间：2026-10-03（本轮施工与验证全部离线完成，0 次真实模型调用、0 次网络出站、0 次部署、0 次 Git 提交）。
- 前置：G3 已完成（V2.R1.3 绑定验收已入 state）；V2.R4.1 done；R4.2 保持 blocked，本切片按计划不等付费 PoC。

## 1. 施工基线（改动前快照）

- `_stage-amz-control/r43-config-byok-20261003/` 内保存 11 份被改文件的原样副本，覆盖：
  `src/providers/v2_registry.py`、`v2_dashscope_semantic.py`、`v2_dashscope_review.py`、
  `v2_dashscope_suite_review.py`、`v2_dashscope_image.py`、`app/product_v2_server.py`、
  `app/server.py`、`.github/workflows/ci-cd.yml`、`config/product-v2/providers.json`、
  `tools/verify_v2_4_1_image_gateway.py`、`.env.example`。
- 改动前逐文件 sha256 已记录在会话工作记录中；registry/providers.json 本轮零修改。

## 2. 交付内容（逐文件）

| 文件 | 变化 |
|---|---|
| `src/providers/v2_credentials.py`（新） | 凭据解析唯一口径：`resolve_default_trial`（`AMZ_V2_DEFAULT_TRIAL` 开关，缺省 fail-closed；非法值抛错）+ `CredentialDecision` + `resolve_credentials`（BYOK > 默认档[受开关约束] > none）。只把 `api_key`/`source` 发给构造方，不进任何对外 payload。 |
| `src/providers/v2_outbound.py`（新） | 出站守护：`validate_outbound_url`（https、无 URL 凭据、端口 443/省略、长度/控制符、私网与 metadata 地址、主机后缀白名单）；`is_private_host` 用 `ipaddress.is_global` 判定 IP 字面量（含 IPv4-mapped IPv6 与带 zone 的 IPv6）；`DEFAULT_ALLOWED_HOSTS = ("aliyuncs.com",)` 只在标准库上实现。 |
| `src/providers/v2_dashscope_image.py` | ctor 增 `allowed_hosts`/`credential_source`；`none` 分支强制 `api_key=""`（环境变量有值也不注入）；`_call` 在传输前调用出站守护（非白名单→`OUTBOUND_POLICY_REJECTED`/internal/503，黑箱重定向继续 `allow_redirects=False`）；新增 `apply_credentials`（BYOK 内存换头）；capabilities 输出 `credential_source`；`create_default_image_provider` 统一走 `resolve_credentials`。 |
| `src/providers/v2_dashscope_semantic.py` / `v2_dashscope_review.py` / `v2_dashscope_suite_review.py` | ctor 增 `credential_source`（`none` 强制 `api_key=""`）；`base_url` 在构造时过出站守护（`http://127.0.0.1:8000` 等一律 ValueError 拒绝）；`analyze/review` 未配置消息区分「默认档关闭」与「未配置密钥」；capabilities 输出 `credential_source`；`apply_credentials` 接缝（语义/复核 BYOK 路线本切片只留接缝，不放行路由）。 |
| `src/providers/v2_fake_image.py` / `v2_fake_semantic.py` / `v2_fake_review.py` / `v2_fake_suite_review.py` | `credential_source="test_double"` + 显式 no-op `apply_credentials`；capabilities 声明同步（替身不持有真实密钥轴）。 |
| `src/providers/v2_registry.py` | DashScope 三条语义/单图复核/整套复核工厂统一改为「注册表条目 + `resolve_credentials` → 构造函数显式注入」；文档字符串同步口径。 |
| `app/product_v2_server.py` | 图像三路由先读并校验 `X-AMZ-Listing-Key-Image`（空白/超长 → 400 `BYOK_HEADER_INVALID`），provider 缺 `apply_credentials` → 400 `BYOK_UNSUPPORTED`（fail-closed 不静默丢弃密钥）；`status_for_failure` 接受 `OUTBOUND_POLICY_REJECTED`→503；`redact()` 扩充 `x-amz-listing-key-*` 头携带值与 Bearer/sk 模式；capabilities 暴露 `credential_source` 与 images 块 `default_trial`（`open/closed/invalid`）。 |
| `.github/workflows/ci-cd.yml` | R4.3 计划要求的火山运行时接线（只接线不读明文）：同步步骤新增 `ARK_API_KEY: ${{ secrets.ARK_API_KEY }}`，两个密钥都缺省才跳过；staging 与远程 `app.env` 同时处理两键；远程 grep 过滤两条键线。名称依据 `image-candidate-review-20261002-seedream.md` §1（Ark 官方文档：`ARK_API_KEY`，`Authorization: Bearer`）。 |
| `.env.example` | 新增 `AMZ_V2_DEFAULT_TRIAL` 注释段（缺省 fail-closed 语义、合法值、BYOK 不依赖该开关）与 `ARK_API_KEY` 注释段（R4.3 只接线、R5.2 落适配器）。 |
| `README.md` | 「凭据口径（V2.R4.3）」段落：默认档开关语义、BYOK 单次请求内存态、`aliyuncs.com` 出站白名单。 |
| `tools/verify_v2_4_1_image_gateway.py` | `request()` 助手支持附加头；新增 V2.4.1-26…-33 八条 R4.3 检查；`-24` 默认 transport 回归显式 `AMZ_V2_DEFAULT_TRIAL=open`；boundary 文本同步。 |

`config/product-v2/providers.json` 未改：registry 条目继续声明 `api_key_env`，凭据解析读取它；
第二 provider（volcengine）条目留给 R5.2（协议本体未实现前不写占位条目，避免「登记≠实现」漂移）。

## 3. 行为语义（验收口径）

1. **闭默认档**：`AMZ_V2_DEFAULT_TRIAL` 未设置/空/`0/false/closed/off` ⇒ `resolve_credentials` 返回
   `api_key=None, source="none"`，适配器 `configured=false`，图像/语义/复核/整套复核真实调用一律
   503 `PROVIDER_NOT_CONFIGURED`（不静默回退到付费档）。`1/true/open/on`（大小写无关）⇒ 沿用部署密钥，
   `credential_source="default"`。任何其他值 ⇒ 构造抛 ValueError（红旗而非猜测）。
2. **BYOK**：仅图像网关三路由接受 `X-AMZ-Listing-Key-Image`；密钥放在单次请求里转交适配器并覆盖
   `Authorization: Bearer <byok>`，与开关无关（用户自有额度）；服务器不落盘、不进 capabilities、不回显；
   替身 provider 显式 no-op；不支持 BYOK 的自定义 provider 工厂 → 400 `BYOK_UNSUPPORTED`。
3. **出站策略**：图像适配器每一次外呼（提交/查询/结果下载）都先过 `validate_outbound_url`：
   必须 https、主机必须匹配 `aliyuncs.com` / `*.aliyuncs.com` 白名单、URL 凭据嵌入、非 443 端口、
   回环/私网/链路本地/测试网段/云 metadata IP、后缀伪装域（`dashscope.aliyuncs.com.evil.io`）
   全部在传输前拒绝（`OUTBOUND_POLICY_REJECTED`，0 次上游调用）；重定向保持 `allow_redirects=False`。
   语义/复核/整套复核 ChatOpenAI 通道的 `base_url` 也在构造时过同一守护。
4. **第二 provider 接线**：CI 在部署到 main 时把 `ARK_API_KEY`（若 GitHub Secret 已配置）写进远程
   `app.env`；R5.2 的注册表条目落地前没有任何真实火山调用路径，对应真实证明保持未证（遵守「未注入前
   对应真实调用保持未证」）。

## 4. 验证证据（全部离线，0 真实模型调用）

| 证据 | 结果 |
|---|---|
| `evals/product-v2/v2.4.1-image-gateway-20261003-062525-r43-solo.json/.txt` | V2.4.1 全套 33 检查全过：含新 -26（开关解析双向+非法值必须抛错）、-27（开关在注册表构造生效，closed 不注入/open 恢复）、-28（出站白名单八反例传输前拒绝且 0 次上游调用）、-29/-30（BYOK 进入 Authorization 且响应/头全部不回显）、-31（closed+有部署密钥：capabilities 仍 200、`credential_source="none"`、提交 503 且 0 次上游调用）、-32（BYOK 绕过默认档开关）、-33（替身 no-op；空白 BYOK 头 400 不看 provider）。-23 磁盘 manifest 零差异（服务无落盘）。 |
| `evals/product-v2/v2.2.2-semantic-provider-20261003-062450-r43-config-byok.json/.txt` | 离线 10/10 全过（含 V2.2.2-10 注册表↔代码一致性）；`--live` 未运行（付费调用无授权）。 |
| `evals/product-v2/v2.5.2-vlm-review-20261003-062459r43-config-byok.json/.txt` | 全过（R01–R21 回归 + 浏览器走查）；`--live` 未运行。 |
| `evals/product-v2/v2.5.5-suite-review-20261003-062832-r43-config-byok.json/.txt` | 全过（整套复核 fake 路由 + 自检）。 |
| `app/server.py --check`（console；亦包含在 V2.4.1-22/ V2.5.2-18/ V2.5.5-11 内） | 38/38 通过。 |
| `tools/check_docs.py --no-run` / `tools/check_project_state.py` / `evals/probes/project_state.py` | 全过（64 向一致；state.md 更新后复跑）。 |
| 额外离线冒烟 | `resolve_default_trial` 空 dict=False、open=True；`create_image_provider` closed→`none`/open→`default`；语义 adapter 拒绝 `http://127.0.0.1:8000` 端点；fake `apply_credentials` no-op。 |

首轮 `v2.4.1-image-gateway-20261003-062230-r43-config-byok` 中 -23 曾标 FAIL：原因是同一时刻并行跑的
`verify_v2_2_2` 把自己的证据文件写进了 `evals/`，manifest 快照捕获到这两个非本轮文件（added 列表仅含
v2.2.2 的 json/txt）；单独重跑（062525-r43-solo）-23 连同全部 33 项全过。这是运行纪律问题（全库
manifest 断言期间不得并写 evals/），不是产品缺陷；首轮证据保留在 repo 中作对照。

## 5. 边界与未证事项（不声称）

- 真实模型调用路径全面未证：本轮无 BYOK 真实密钥、无网络出站、无付费调用；DashScope 真链证据与
  R4.2 火山 PoC 保持各自独立门。
- 语义/复核/整套复核路由暂不读取 BYOK 头（只留了 `apply_credentials` 接缝与 `-33` 的替身 no-op 合同）；
  语义 BYOK 消费面属于后续任务接线，不得把本切片理解为语义端已支持 BYOK。
- DNS 解析层重绑定残余不能由本守护消除（守护只判定 URL 与 IP 字面量，不做 DNS 拨号前解析）；
  「远程 localhost 不等于用户本机」的部署边界在计划 §R4.3 文本中，运行时由绑定 127.0.0.1 + 白名单共同兜底。
- 入站其他 `X-AMZ-Listing-*` 头无论何值都被服务器忽略（不转发给任何上游）；这消除了把外来头当凭据
  的通道，但也意味着「危险头黑名单」当前以「唯一白名单头 + 适配器固定头集」实现，不是通用反例黑名单。
- BYOK 密钥防重放/限速均未实现（默认路由本机绑定，Caddy 层无认证）；T7/G01 设置 UI（可见能力与非秘
  密身份、BYOK 内存输入）属 R6.3，不在本切片。
- 默认档「在访问范围与可执行消费限制获批并验证前保持关闭」已按计划文字执行为 fail-closed；获批后的
  形态（限额/审计策略）仍属 R4.2/R6.3 后续。
