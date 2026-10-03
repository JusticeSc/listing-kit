NOT-AUTHORITY: point-in-time verification evidence only, not a plan, current state, or product completion.

# V2.R7.1 完整验证（2026-10-03 19:50Z）

结论：R7.1 全部闭合。离线回归、语义/VLM 最小真实调用、两生图模型当前树新鲜重证均通过；
刷新 shell 后 ARK 通道恢复，火山阻塞已解除，不再沿用旧 run3 凑数。

## 1. 两轮完整离线回归（当前树最终代码）

- 证据：`evals/product-v2/v2.7.1-regression-20261003-r71f-final.txt` /
  `evals/product-v2/v2.7.1-regression-20261003-r71f-final.json`
- 40 条命令 × 2 轮 = 80 行全部 rc=0，problems=0，指纹两轮一致
  `9825912a9a3a23845cc025698a73f60df0bbd1c01d0189cfe8cc7a682936f3d3`。
- 证据生成后 `app/`、`src/`、`config/`、`tools/` 无更新文件（0 个比证据新的文件），
  故回归结论仍绑定当前树，无需重跑。

## 2. 语义最小真实调用（预算内，当前树）

- 证据：`evals/product-v2/v2.2.2-semantic-provider-20261003-194132-r71-semlive.json`（live=true，
  12/12 passed，含 L1 真实正例 + L2 无效密钥负例）。
- L1：`deepseek-v4.1-flash`，prompt 1231 + completion 2127 tokens（含 reasoning 1663），
  request `chatcmpl-bbf6f5be-96da-9f5c-b33d-d3474cc8b95d`，6 槽全 proposed、带证据与置信度。
- L2：无效密钥正确归为 PROVIDER_AUTH_FAILED / fatal，不重试，0 计费。
- 费用（官方北京价忙时保守）：输入 2元/M、输出 8元/M → 约 0.0195 元，预留 0.02 元。

## 3. VLM 最小真实调用（预算内，当前树，公开许可素材）

- 证据：`evals/product-v2/v2.5.2-review-live-20261003-194238r71-vlm.json`（status checked，
  binding_ok true）。
- `qwen-vl-max`，候选与参考图同为 honey-jar-antique.jpg（sha256 c024b7cf…，2239735 字节），
  prompt 3101 + completion 38 tokens，request `chatcmpl-3256e900-3fd2-95bb-8220-fd86bee61639`。
- 费用（官方北京价）：输入 1.6元/M、输出 4元/M → 约 0.0051 元，预留 0.01 元。
- 不评估检出质量；VLM 未确认事实、未采用图片、未制造硬 BLOCK。

## 4. 两生图真实链（当前轮状态）

- DashScope qwen-image-3.0 当前树新鲜重证通过：
  `evals/product-v2/v2.4.5-live-reference-20261003-194526-r71-dashscope2.json`（5/5 passed，
  submit 1 / status 5 / result 1，同素材 c024b7cf…，2239735 字节，1 张，0.20 元）。
  需 `AMZ_V2_DEFAULT_TRIAL=open`；未设时 fail-closed（194502 证据，0 上游调用，0 费用）。
- 火山 doubao-seedream-5-0-flash-260915 当前树新鲜重证通过：
  `evals/product-v2/v2.4.5-live-reference-20261003-195600-r71-volc2.json`（5/5 passed，
  同步 submit 1 / status 0 / result 0，task_id null，同素材 c024b7cf…，2239735 字节，
  1 张，0.12 元）。刷新后 shell 中 `ARK_API_KEY` 长度 36（值不记录），`AMZ_V2_DEFAULT_TRIAL=open`。
- 生图小计：历史已耗 0.56 + 本轮 DashScope 重证 0.20 + 本轮火山重证 0.12 = 0.88；
  语义/VLM 本轮 0.03；合计 0.91 / 5.0 元，次数 image 6/8、semantic_vlm 3/4、total 9/12，
  均未到停线。台账：`_working/amz-listing-kit-product-v2/budget-ledger.json`（11:57Z）。

## 5. 素材与密钥纪律

- 素材：`walkthrough-assets/food/honey-jar-antique.jpg`（c024b7cf…），CC BY 2.0 Cindy Shebley。
- 密钥：只记录存在性/长度与通道名，不打印、不导出、不入证据正文；BYOK/默认档判据由离线回归覆盖。
- 失败保留：194502（默认档关闭）保留原样，未重提、未重试。

## 6. R7.1 验收对照（适用范围）

- 两轮离线回归全绿且指纹一致：proven（r71f）。
- 两模型必要真实链：两模型当前树均 proven（DashScope 194526 + 火山 195600），R7.1 可进发布。
- 语义/VLM 所需最少调用：proven（各 1 次正向 + 语义 1 次无效密钥负例）。
- secret/磁盘/出站策略反例：由回归内含的 R4.3/R6.3 网关与包审计覆盖，未新增框架。
- 已知 boot 间歇：仍 Unknown，不因本轮绿色关闭，转 R7.4/RC19 继续携带。
