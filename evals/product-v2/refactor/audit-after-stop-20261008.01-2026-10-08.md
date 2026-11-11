<!-- 拆分件 01/03 · 父文档 evals/product-v2/refactor/audit-after-stop-20261008.md -->
# 停工后的工程审计、状态核对与后续规划（2026-10-08）
[返回 audit-after-stop-20261008.md](audit-after-stop-20261008.md)

# 停工后的工程审计、状态核对与后续规划（2026-10-08）

> NOT-AUTHORITY：本文件仅保存本次时点观察与规划建议。目标/任务/权限取 `docs/product-v2-refactor-plan.md`；结构准出取 `docs/product-v2-refactor-design.md`；恢复前沿只取 `_working/amz-listing-kit-product-v2/state.md`。
> 最新请求仅为审计、确定状态与规划；此前“结束当前工作”未被解除。本轮不恢复施工、不改产品/验证器/CI/依赖、不提交推送部署、不删除V1、不调用付费模型。

## 1. 结论

当前是**已发布、可启动的 Product V2 候选 + 未完成的完整工程验收 + 独立停放的 V1 清理 WIP**，不是空壳，也不是工程Goal完成。

1. 上次未观察完的 main 发布已经成功，不能继续称“线上发布未知”。
2. V1清理没有进入main或线上；停工分支不可合并。旧恢复说明存在分支材料可达性和验证范围错误。
3. RC19启动/载入间歇仍缺现象—机制对应，最终同候选两轮、完整真实辅助任务与适用矩阵仍未成立。
4. main的分支保护和独立review没有成立证据；本次API直接返回 `protected=false`、规则为空、PR #5 reviews为空，不能声称受保护审查已完成。
5. 原state的8/10不是当前剩余额度。随后至少有新的探针/取样/构建/V1工作段；继续施工前必须处理原10轮停止门，不自动再给两轮。
6. 本轮只纠正state的用户停工阻塞，不把真实active系统Goal伪造为paused或completed，不修改正式验收标准。

## 2. 基准与当前落点

| 对象 | 本次直接观察 | 范围与限制 |
|---|---|---|
| 当前检出 | main `0572b5c9c042502b77fb2a5e302f5775bbfd46fc`，审计开始工作树干净 | 本轮结束只新增审计证据/原文备份并修改state；不提交 |
| GitHub main | 同一 `0572b5c` | 没有fetch/checkout/reset/rebase等变异操作 |
| 停工WIP | 本地 `feat/v1-sunset-20261008`，`15faa65` | 相对main：126文件，114删除、3修改、9新增恢复/快照文件；未checkout或执行WIP |
| 系统产品Goal | 原生 `goal.get`：`159d03ed410f9ff9`，active | 正文sha256 `bac1155dbef21876391328dafd50a5624dee8461388754021a31aa59ff1c6fc6`，匹配计划§2.1；active不解除用户停工 |
| 正式进度 | R5.1未完成；R5.2/5.3、R6.1–3、R7.1–5仍pending，R6.4仅历史范围done | 不以CI或本次审计把任何整项标done |
| 本轮证据 | 同前缀 `audit-after-stop-20261008-observations.json` | 原生Goal/GitHub观察、发布工件、可信HTTPS页面/资源hash及计数口径 |

比较范围：停工WIP用 `git diff 0572b5c...15faa65`；已合并差量沿上一审计基准 `132884d...0572b5c`；当前代码与分支blob分开，快照副本不当活代码。

## 3. 发布：已经成立的事实与尚未成立的合同

### 3.1 当前发布已确认成功

- [PR #5](https://github.com/JusticeSc/listing-kit/pull/5)：2026-10-08T10:36:30Z merged，merge `0572b5c`。
- [main run 37764592110](https://github.com/JusticeSc/listing-kit/actions/runs/37764592110)：completed/success；两个job均success，结束于10:58:44Z。
- 实际job日志：Docker构建/health smoke；真实隔离容器selftest **32/32**；真实脚本离线故障类别 **13/13**；远端Docker deploy；可信HTTPS页面 **10/10**；源码/配置/镜像指纹；finalize；工件上传均成功。日志中 `release_finalize_rc=0`，previous已清理；本次没有执行新的回退。
- selftest的ST-DEAD FAIL是必须失败的不可达负例，外层ST-09据此PASS，不是成功发布中的产品红。
- selftest已在真实镜像origin做页面保存/刷新/项目包往返，并有不同image ID、同origin代表项目的文档/Blob/采用保全；这是隔离marker A/B版本的机制证明，不等于对两份真实历史产品版本做过生产回退。
- 线上PS是空项目新建/刷新/项目ZIP下载导入，不证明商品事实→真实生成→返工→采用→交付完整任务，也不证明线上代表项目跨产品版本恢复。

发布工件：[artifact 11545870528](https://github.com/JusticeSc/listing-kit/actions/runs/37764592110/artifacts/11545870528)，已下载到工作区 `releases/audit-37764592110/`，未改线上。

| 身份 | 工件值 |
|---|---|
| commit | `0572b5c9c042502b77fb2a5e302f5775bbfd46fc` |
| image ID | `sha256:ce90236c206c8a87d7ee41d53926b62cf23d2e6aa781f75f80a6f957a63c5649` |
| runtime SHA256 | `44f2e9b9a00c2d8fd870ed0adf71baf7bdd6b2cabaa2f059c2b0870b75e43d30` |
| public configuration SHA256 | `752430317ec03bc99e24ea2ef0bfadddd200ae7694f6c61844ef0e1dc885af51` |
| Caddy SHA256 | `e375655dcf81ada9a4ac315ceaf1791bbdf1c9ba3bb0aab0f529fc6eae4de176` |
| runtime实际枚举 | 85文件，default_trial=closed；没有旧V1/fixture路径 |

本次独立Chrome无头临时profile访问 `https://47.115.172.233:8080/`，保留TLS验证：首页200、secureContext=true、新建按钮就绪，health/capabilities=200、默认付费档closed，console/page/requestfailed均空。首页/styles/entry/app/workspace/generation/adoption/delivery八个实际HTTP资源hash全部匹配当前工件。仅GET/首页观察，不创建业务项目、不发模型请求；没有SSH读取宿主当前image ID，发布时工件身份与当前公开资源一致分别陈述。截图 `../evidence/audit-after-stop-20261008-home.png`（实际756×481，不冒充1366或真实缩放验收），浏览器/profile已释放。

### 3.2 审查/保护与准出不能借绿灯放行

GitHub当前只读API：main `protected=false`，protection.enabled=false、required status checks为空；`rules/branches/main=[]`。PR #5 `reviews=[]`、reviewDecision为空。CI成功和合并事实成立；独立审查/保护合同不成立，不能用“现有流程”字样假装有强制保护。后续发布前应设置并验证既定检查/审查要求；本轮不改GitHub设置。既有RC19和最终验收仍未完成，已经发布的事实不能反向证明计划§7.6/§7.7所有产品准出成立。

