# 可信基线发布收尾（2026-10-17/18）

## 授权范围回顾

用户 2026-10-17 明确："授权，由你全权负责尽最大努力交付可信基线"，触发器选定：PR #13 转正合并 + 部署链跟到 finalize（失败回滚），范围仅本轮基线，真人门用户稍后亲自走。不含收费/真实模型/供应商外发/封存下一版 WIP。

## 交付结论

| 项 | 值 |
|---|---|
| main | `2c4a33a77941d72ca7c8d6c80e23c92e7f6f367b` |
| 线上镜像 | `amz-listing-kit:2c4a33a77941d72ca7c8d6c80e23c92e7f6f367b` (image_id `sha256:f71c5db26d513a226ff323746fb01ff57b8fbac3c078e9bff770ca19510a9e4c`) |
| 容器状态 | healthy，仅 1 个应用容器 + 1 个 TLS 容器，无 `-previous` 残留 |
| 事务状态 | 已 finalize，无 open 事务文件 |
| CI run | `39045865774` success（push event，main 自动部署） |
| 运行时指纹 | `a1e73bdc3454a994213fe59b9ae5ea5c3034da20573bca9f2072f040e79d8de1` |
| 指纹相等 | 线上 vs CI 候选：files(93) + served(69) + public_configuration 全等 |
| acceptance | HTTPS 页面 12/12 通过 |
| 默认试运行 | closed（fail-closed 生效） |
| 证据留档 | `evals/product-v2/refactor/baseline-release-20261017T154245Z/`（artifact 12105698120；本目录为原 `_stage-amz-control/` 下同名工作区目录的入库副本）|

## 合并链

- `a278044` — CI `39035149699` success
- `77c84aa` — CI `39036915488` success（state 授权指针）
- `a06bd34` — CI `39038112521` success（V2.3.5-07 收口 / dev 残留清理）
- merge `82dc0ff` — PR #13（第 1–5 批基线）
- `274fea2` — PR #14（行尾政策：`*.toml/*.lock/*.txt eol=lf`）
- merge `9c835dc`
- merge `2c4a33a` — PR #15（state 同步）

旧红 CI `39033126782` / `39034753449` / `39039525655`（远端构建超时取消）保留不洗绿。

## 途中真实故障与处置

1. **CRLF 污染指纹不等**：远端构建上下文用 Windows 工作区 tar（CRLF），CI 候选为 LF，3 文件（pyproject.toml / uv.lock / lit-html.LICENSE.txt）字节不一致。
   - 处置：按事务语义 rollback（previous `4bf6d03` + Caddy 配置恢复，两次实测生效），提交 `.gitattributes` 新规则（PR #14），确认 `git archive` 输出 LF 后重建。
   - 教训：Windows 机器上 `git archive` 受 `.gitattributes`/`core.autocrlf` 影响会转 CRLF；必须先提交 LF 规则到树，`git archive` 才输出仓库 LF 字节。
2. **CI 撞 open 事务**：main push CI 想 deploy 新镜像，但远端有 open 事务（我手动 LF 版），脚本正确拒绝；CI 的 rollback 因 image 身份不匹配也正确拒绝，什么都没动，线上未受影响。
3. **远端构建超时**：run `39039525655` job 级 20 分钟超时取消，deploy 事务未开始，线上仍旧版。

## 边界（不越界声明）

- 这是"工程基线可信"：代码 / 测试 / 发布链 / 身份链闭环。
- **不等于**原产品 Goal 完成；原产品仍 paused、7/10 批、52/52 生图、费用账本不变。
- **不等于**下一版 WIP 已上线（WIP 另行封存）。
- **不等于**体验成熟。
- 本轮零新增付费调用；未做 V1 清退。

## 真人门

C15 按计划合同保持 open（须首次参与的独立用户无干预走完，sponsor 亲验不等同 C15）。C17 及用户 2026-10-17 亲自走完的亲验（原话："我确认过了做好收尾吧"）记为强通过信号，非助手代签。