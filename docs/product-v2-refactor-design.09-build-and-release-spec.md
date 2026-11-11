<!-- 拆分件 09/29 · 父文档 docs/product-v2-refactor-design.md -->
# 实施规格：构建、发布与回退
[返回设计目录](product-v2-refactor-design.md) · [上一主题](product-v2-refactor-design.08-lifecycle-reports-and-exports.md) · [下一主题](product-v2-refactor-design.10-packet-responsibilities-and-validation.md)

### 10.7 TS→浏览器→镜像：一个源码，完整产物，失败不半生成

`tools/build_product_v2_ts.mjs` 从compiler program取得**批准范围 `app/product_v2/**` 内全部实际TS源码**，排除 `.d.ts`、外部node_modules/vendor；不能仅用parsed.fileNames漏掉传递import，也不全仓迁TS。输出稳定排序、现有ESM/LF/header，同名JS唯一由TS生成。

先对全program做diagnostics；再在内存收齐全部transpile输出及诊断，全部通过后才写。`--check`只比较完整集合、不写。构建阶段失败不能前几个JS已写、后一个失败；filesystem中途故障仍不承诺多文件原子，应保留失败并用该批精确快照恢复整组。不得手补生成JS或跳过严格类型。

2026-10-06四份新TS/旧Interface不相容的风险已由组A处理；当前完整集合和消费者继续受本节约束，不重新发射旧authorization或重做该迁移。后续仅对真正改变的owner及全部调用/restore消费者同包切换；`jsconfig.json`、生成一致性、CI、正式HTML import与Docker白名单闭合。生产保留必要生成JS/vendor/license，排除compiler/TS源/evals/fake；真实服务字节与源码产物比对，不检查文字“看起来COPY了”。

### 10.8 发布/回退：保留既有事务平台，补真实不同版本证明

仅修改现有 `deploy/release-transaction.sh`、`tools/release_transaction_probe.py`、`.github/workflows/ci-cd.yml` 及实际受影响Docker白名单，不新建CD。以现有 `release-transaction/v1` journal为准：baseline（变更前落盘）→parked→new_started→new_healthy→TLS备份/安装意图/安装完成→tls_converged→https_ok；持久phase与镜像/容器身份核对，开放或不匹配事务禁止下一部署，不能猜测半停车状态。

- previous容器、旧可运行镜像与必要非秘密配置/TLS备份留到外部可信HTTPS、静态资源、隔离Chrome页面主链、源码/镜像/配置指纹都完成，且finalize再次验证之后。deploy不提前清旧版本。
- deploy/外部页面/指纹失败，或finalize可恢复验证失败（现有退出码1）进入rollback；finalize身份拒绝或已开始清理后的失败（现有退出码4）保留明确manual状态，不假称旧版完整保留，不盲删当前服务。恢复失败保留journal和准确失败，不报发布成功。
- fingerprint保留现有全部app/src/config、锁文件、能力公开配置的覆盖，再核对实际生成且服务的JS、镜像ID/tag、Caddy hash；**不能把范围缩成“TS输出∩静态目录”而丢Python/config**。default_trial必须closed，secret永不取hash/输出；SSH现有keyscan仅TOFU，不是独立身份背书，不扩大Secrets/信任授权。
- 沿用现已实现的正式Dockerfile两独立context和markerA/B、不同image ID及late-failure断言；不要重新设计镜像回退。仍须在获批Linux环境真实运行，并将容器页面证明绑定到被测image实际服务的origin，不能把另起本地测试服务器的页面算进去；finalize失败保留previous/journal/备份，rollback核对ID及marker回A，另一轮成功finalize另证。
- 容器/配置回退与浏览器数据恢复分别判定。发布前代表同版本完整项目ZIP与hash在批准独立Chrome中导入打开；回退后在**同一可信origin**验证包/Blob/历史，而不是换端口空库。不能以服务重启宣称IDB恢复，也不以改格式后旧应用强读新库替数据恢复。
- Linux Docker/TLS在获批CI/部署环境运行；本机Windows缺运行时不伪造绿灯。页面只用批准Chrome无头/独立profile；缺Chrome/信任证书为精确阻断，不静默扩大浏览器或用 `curl -k`。smoke不调用付费模型。

