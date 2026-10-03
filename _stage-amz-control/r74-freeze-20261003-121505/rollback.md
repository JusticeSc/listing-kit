# R7.4 发布冻结 · 回退基线（20261003-121505）

NOT-AUTHORITY: point-in-time rollback baseline only.

- pre_release_head: `ed363d329de7111d2cae07c56a30f228150d3fbe`
- scope: 87 tracked dirty + 17 new key files + 9 R7.1 evidence = 113 files
- scope_fingerprint: `daeee0429806c41fde23b55603cf551f5dc95b148ed629e89fa055ce71d5a032`
- deploy_fingerprint: `d0dc166ebb686e6902b38d96156b1be08471d53ea01d14f922d8005d9ff8ab0d`
- manifest: `manifest.json`（本目录，含逐文件 sha256/size）

## 回退

- tracked 87 件：`git checkout ed363d3 -- <manifest.tracked_dirty.files[].path>`，或保留工作区则 `git stash`。
- new key 17 件（plan/verification.json/generation.js/session.js/config-export.js/verification_policy.py/check_verification.py/refactor_resume.py/session_lifecycle Verifier/two_adapters Verifier/check_frontend_versions/volcengine_image/credentials/outbound/package.json/package-lock.json/jsconfig.json）：HEAD 无版本；备份已删以保 CI `Reject verification side effects` 干净，提交前靠工作区原文件，提交后靠新 commit 恢复。
- R7.1 证据 9 件（`git add -f` 提升）：提交后靠新 commit 恢复；提交前本地原文件即权威。
- state/budget：`state.md` 随提交走；`budget-ledger.json` 本地忽略、不进库（spent 0.91/5.0 CNY，image 6/8、semantic_vlm 3/4、total 9/12）。
- 远端运行时回滚：CI `Build on remote Docker and deploy with rollback` 保留 previous 容器，health 失败自动 rename 回去。

## 秘密复核（提交前已扫）

- 6 件历史正则命中经逐件核对均为 fixture/占位（`task-*/act-*`、`sk-fixture-only`、`task-default-transport`），无真值。
- 增量 diff 无 `API_KEY=<value>` 真值行；`.env`/`app.env` 本地均不存在。
- `artifact_check`（根目录旧预算草稿）不在提交范围，不进库。

## R71 绑定确认

- R71 报告 mtime 之后 `app/src/config/tools` 0 newer；r71f 40×2 全绿指纹 `9825912a9a3a2384…` 仍绑当前树。
- `audit_v2_7_4_completion.py` 仅旧 C1–C17 存在性预检，不当 R7.4 proven 证据；R7.4 矩阵按计划 §10 RC01–RC17/RC19/RC20工程项另行冻结。
