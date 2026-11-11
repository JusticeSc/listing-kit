<!-- 拆分件 01/02 · 父文档 evals/product-v2/refactor/packet10-release-rollback-20261007T173500.md -->
# 包10 第一片：release 脚本/probe 两 image 版本回退证据
[返回 packet10-release-rollback-20261007T173500.md](packet10-release-rollback-20261007T173500.md)

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

