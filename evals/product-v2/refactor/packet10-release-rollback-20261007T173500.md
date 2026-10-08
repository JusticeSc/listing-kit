# 包10 第一片：release 脚本/probe 两 image 版本回退证据

> 时间：2026-10-07T17:35+08:00（stamp 20261007173107 轮）· 本地离线证据，不真实部署、不读密钥、不碰 V1。
> 范围：只碰 `deploy/release-transaction.sh`（换行修复）、`tools/release_transaction_probe.py`（新增 `--offline-rollback`）、`.gitattributes`（`*.sh eol=lf`）、本证据文件。未碰 `.github/workflows/**`、`Dockerfile*`、`app/**`、`src/**`。
> 结论：发布事务失败路径回退语义成立——真实脚本 deploy→finalize 晚期失败（exit 1，previous/journal/备份保留）→rollback（exit 1）回到旧版本；prev/current 两版本指纹确实不同。`--selftest` 真实容器/TLS/HTTPS 证据仍需 Linux 获批环境跑，本片不替代。

## 1. 要求对照（设计 §10.8 / 计划 V2.R7.4 / §7.4 / §7.7）

- 设计 §10.8：previous 容器、旧可运行镜像与非秘密配置/TLS 备份留到外部可信 HTTPS、静态资源、隔离页面主链、指纹都完成且 finalize 再次验证之后；deploy 不提前清旧版本。
- 设计 §10.8：deploy/页面/指纹失败或 finalize 可恢复验证失败（exit 1）进 rollback；finalize 身份拒绝或清理后失败（exit 4）为 manual，不假称保留、不盲删。
- 设计 §10.8：修正 selftest 同一 image 换 tag 问题——两个独立上下文、仅实际服务静态 marker 不同、分别 build、先断言真实 image ID 不同。
- 计划 §7.7：previous 保留到容器健康+受信 HTTPS+静态+页面主链验收结束；任一必要失败进回退；同一 origin 恢复旧服务并核对可用性；`--page-smoke` 做事务外验收、`--selftest` 做事务机制证据；探针 green 不证明某次真实部署成功。
- 计划 §7.4：服务回退恢复对应代码/镜像/非秘密配置；数据恢复用同版本库或对应项目包，两者不互冒；浏览器数据恢复另证，不以容器重启宣称 IDB 恢复。
- 计划 V2.R7.4：按 §7.7 修发布回退缺口；旧版本保留到全部必要验收结束；失败回退并实际核对。

## 2. 改动/新增文件

| 文件 | 改动 |
|---|---|
| `tools/release_transaction_probe.py` | 新增 `--offline-rollback` 模式（OR-00–OR-07，约 360 行）：OR-01/OR-02 真实跑脚本纯文本路径；OR-03–OR-07 在 PATH 前缀注入最小 stage 执行器（fake docker/curl/sleep，只复刻进程边界行为）后真实跑脚本 deploy→finalize 晚期失败→rollback→回退核对全链。同步 docstring 与 CLI 用法行。 |
| `deploy/release-transaction.sh` | 零语义改动：工作树 CRLF→LF（此前 WSL bash 报 `set: pipefail: invalid option name`，脚本完全无法执行）。 |
| `.gitattributes` | 新增 `*.sh text eol=lf`，防脚本换行回退。 |
| 本文件 | `evals/product-v2/refactor/packet10-release-rollback-20261007T173500.md`（本片证据）。 |

## 3. 真跑证据

### 3.1 探针全绿（命令+退出码+原始输出）

命令：`uv run --locked python tools/release_transaction_probe.py --offline-rollback` → `PROBE_EXIT=0`

```
========================================================================
发布事务离线回退证据：真实脚本 + 最小仿真执行器
========================================================================
  [PASS] OR-00 bash 可用
  [PASS] OR-01 真实脚本无参返回用法错误 exit 2
  [PASS] OR-02 无开放事务 finalize/rollback 均 exit 4 且 HOME 零副作用
  [PASS] OR-03 两版本 image 指纹确实不同（不用同一 image 换 tag 充数）
  [PASS] OR-04 真实 deploy 开放事务并保留旧容器/配置（previous 未提前删）
  [PASS] OR-05 坏静态 finalize 判红 exit 1 且 previous/journal/备份保留
  [PASS] OR-06 真实 rollback 回到旧 image/marker A 并清除事务（两版本指纹不同）
  [PASS] OR-07 回退后无开放事务（stale finalize 拒绝 exit 4）且旧服务/配置完整
结果：8/8 通过，0 失败。
```

各检查语义（断言全部走真实脚本退出码+持久化文件，非仿真回声）：

- OR-01：真实脚本无参 → exit 2 且 stderr 含用法行。
- OR-02：隔离 HOME 下无开放事务 finalize/rollback → 均 exit 4，且不创建事务文件。
- OR-03：两版本指纹不同（tag 名不同 + sha256 不同，见 §3.2）。
- OR-04：真实 deploy → exit 0，serving=新 tag、previous=旧 tag 停放、事务 `PREVIOUS_EXISTED='true'`+`PHASE='https_ok'`、Caddy 备份落盘。
- OR-05：注入坏静态（health 仍绿）→ finalize exit 1，previous/journal/备份保留，live Caddy≠旧配置。
- OR-06：真实 rollback → exit 1，serving 回到旧 tag、previous 容器消失、事务清除、Caddy 恢复旧字节、服务 marker 回 A。
- OR-07：回退后 stale finalize → exit 4，旧服务/配置完整，无残留开放事务。

### 3.2 两版本指纹（必须不同）

本轮 stamp `20261007173107`（每次运行 stamp 变化，指纹随之新鲜生成）：

- old_tag：`amz-release-offline-old:20261007173107`
- new_tag：`amz-release-offline-new:20261007173107`
- old_image_id：`sha256:842efd1851ec9075480cca5b7420897f8aac7f397e305fee7f5622cd3909b77f`
- new_image_id：`sha256:fdb8ff0848acda6befb9433832c7fd7b7c230b83d039f3227dd6ea4bc53c4f9c`
- 回退前服务 marker：`release-marker-b-20261007173107`（OR-04 deploy 切到 B）
- 回退后服务 marker：`release-marker-a-20261007173107`（OR-06 回到 A，B≠A，真回退非原地重启）

独立复核：重跑同命令即生成新 stamp 新指纹；`OR-03` 对 tag 名+sha256 双重断言不同；`OR-06` 对回退前后 marker A≠B 断言。

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
