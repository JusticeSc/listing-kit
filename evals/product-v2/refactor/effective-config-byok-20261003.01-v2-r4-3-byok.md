<!-- 拆分件 01/02 · 父文档 evals/product-v2/refactor/effective-config-byok-20261003.md -->
# V2.R4.3 · 统一有效配置 / BYOK / 出站策略 — 施工时点报告
[返回 effective-config-byok-20261003.md](effective-config-byok-20261003.md)

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

