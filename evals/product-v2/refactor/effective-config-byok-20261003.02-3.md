<!-- 拆分件 02/02 · 父文档 evals/product-v2/refactor/effective-config-byok-20261003.md -->
# 3. 行为语义（验收口径）
[返回 effective-config-byok-20261003.md](effective-config-byok-20261003.md)

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
