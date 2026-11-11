<!-- 拆分件 02/02 · 父文档 evals/product-v2/refactor/packet10-release-rollback-20261007T173500.md -->
# 3.3 回退后状态核对（OR-06/OR-07 实际断言）
[返回 packet10-release-rollback-20261007T173500.md](packet10-release-rollback-20261007T173500.md)

### 3.3 回退后状态核对（OR-06/OR-07 实际断言）

- serving 容器身份 == old_tag（旧版本，非新 tag）。
- previous 容器文件消失（已被 rename 恢复为 serving，无残留 `-previous`）。
- 事务文件不存在（`clear_open_transaction` 已清，无开放事务）。
- Caddyfile 字节恢复旧配置（语义相等；`install` 恢复吞末尾换行，探针按 `rstrip("\n")` 归一核对——细节见 §4.2）。
- 服务 marker 回到 A。
- 回退后再调 finalize → exit 4（无开放事务拒绝），旧服务/配置完整。

### 3.4 七闸门（逐条命令+退出码）

| # | 命令 | 退出码 |
|---|---|---|
| 1 | `node --check app/product_v2/workspace.js` | 0 |
| 2 | `npm run build:frontend` | 0 |
| 3 | `npm run check:types` | 0 |
| 4 | `npm run check:generated` | 0 |
| 5 | `node --test evals/product-v2/node/*.test.mjs`（227/227 pass） | 0 |
| 6 | `uv run --locked python tools/check_project_state.py`（全过） | 0 |
| 7 | `uv run --locked python tools/check_docs.py --no-run`（全过） | 0 |
| + | `uv run --locked python tools/release_transaction_probe.py --offline-rollback`（8/8） | 0 |

## 4. 缺口与诚实声明（先写证据再修 / 如实报告，不掩盖）

### 4.1 真实缺口：本机无 Docker daemon，`--selftest` 未跑

- 本机 `docker info` 连不上 daemon（`npipe:////./pipe/dockerDesktopLinuxEngine` 不存在），`--selftest`（真实容器/TLS/HTTPS）在此环境精确阻断。
- 本片 `--offline-rollback` 只证明事务状态机在失败路径上的回退语义（真实脚本+最小进程边界仿真），**不替代** `--selftest` 的真实容器/TLS/HTTPS 证据。
- 未决：Linux 获批环境（Docker daemon + Playwright/Chromium）仍须跑 `tools/release_transaction_probe.py --selftest` 全绿；真实部署的回退仍需按事件单独核对（探针 docstring 原话）。

### 4.2 仿真边界（本片如实声明，非产品缺陷）

- stage docker/curl/sleep 只复刻进程边界行为（容器名集合、inspect/health 字段、Caddy 字节、HTTPS/静态判据）；脚本内部编排（park/rename/restore/cleanup/journal）一律走真实脚本，不复制。
- 两版本 image 为不同 sha256 内容对象断言（tag+digest 双重），不用同一 image 换 tag 充数；但毕竟是 stage 侧声明的 digest，非真实 `docker build` 产物——真实构建差异证明仍归 `--selftest`（ST-02-IDs）。
- `install` 恢复 Caddyfile 会吞末尾换行：OR-06/OR-07 按 `rstrip("\n")` 归一核对字节语义，不钉死换行差异。脚本行为本身符合“备份写回”，属 coreutils `install` 语义，非事务缺陷。
- OR-02 的“不触碰服务”后置在无 daemon 本机退化为 HOME 零副作用（无事务文件创建）；真实“原服务不变”核对在 `--selftest` ST-04。

### 4.3 本片发现并已修的真实缺口：脚本 CRLF 导致 Linux 完全无法执行

- 现象：`deploy/release-transaction.sh` 工作树为 CRLF，WSL/Linux bash 执行即 `line 22: set: pipefail: invalid option name`，deploy/finalize/rollback 任一入口都进不了（本片 OR-01/OR-02 初跑即红，证据见探针开发过程）。
- 定性：发布事务脚本在 Linux 侧**完全不可执行**——比“删 previous 缺口”更前置的真实阻断。
- 处置：先写证据（探针红），再修——工作树转 LF + `.gitattributes` 加 `*.sh eol=lf`。零语义改动（`git diff` 对该脚本无内容差，仅换行）。
- 为何此前未发现：仓库 `.gitattributes` 只给 `*.py/*.js/*.mjs/...` 强制 LF，`*.sh` 漏网，Windows 检出即 CRLF。

### 4.4 现有流程“删 previous”核对结论

- 静态审计 `deploy/release-transaction.sh`：`docker rm --force` 仅出现在三处——(a) 回退时删失败的新容器（`restore_app_container` new_started=true 分支）；(b) 回退时删本次新建的 TLS 容器；(c) finalize 清理 previous——且 (c) 在健康+HTTPS+静态重验证全过之后。deploy 全程无删 previous；脏恢复点（serving+previous 并存无事务）deploy 直接拒绝 exit 1，不自动删。
- 工作流 rollback 门（只读核对 `.github/workflows/ci-cd.yml:398`，本片未改）：deploy/acceptance/fingerprint 失败或 finalize recoverable（exit 1）失败才进 rollback；exit 4 不自动回滚，需人工清理。与脚本退出码契约一致。
- 结论：现有流程无“healthy 后提前删 previous”缺口（该缺口已由此脚本修复，注释与事务语义一致）；本片未发现新的提前删除点。

### 4.5 数据恢复边界（§7.4，未证项）

- 本片只证服务/配置回退（容器身份+Caddy 字节+事务清除）；浏览器数据恢复（同 origin 完整项目 ZIP 导入/Blob/历史）另证，不以容器回滚冒充——按计划 §7.4/§7.7，该项仍未证，归包10 后续片或包11。

## 5. commit 记录

- 本片只 add 本片文件，不 push（按包10 第一片边界）。
- commit 信息含 `packet10`（执行时贴实际 hash）。
