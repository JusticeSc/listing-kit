# Product V2 正式 Goal 恢复前控制收口 · 2026-10-01 11:58:05 +08:00

NOT-AUTHORITY: point-in-time verification evidence only

## 触发与红证据

1. V2.5.5、V2.UI.2 已在 current state 标为 `done`，但三份施工任务书和 INDEX 仍标 `draft`；
   修复前 `tools/check_docs.py --no-run` 退出码仍为 0，说明身份漂移没有守卫。
2. 在本地放入时间更晚、未进 Git 的 `v2.1.1-indexeddb-20990101-000000-control-probe.txt` 后，
   修复前 `audit_v2_7_4_completion.newest()` 会选中该文件，说明本机过程输出可以污染完成矩阵。
3. CI 的副作用检查只执行 `git diff --exit-code`，不会报告未跟踪文件；验证器产生的大量时点报告因此
   能在本地长期累积而不被控制链识别。

## 收口结果

- Product V2 新生成的顶层 TXT/JSON/MD 与截图默认被 `.gitignore` 排除；已入库证据不受影响，新的
  长期证据必须按计划 §14 使用 `git add -f -- <精确路径>` 提升。
- 完成矩阵只从 `git ls-files` 返回的 Product V2 证据中选择最新文件。本地放入同名未来报告后，
  `newest()` 仍选择已跟踪的 `v2.1.1-indexeddb-20261001-100808.txt`。
- CI 副作用门改为检查 `git status --porcelain --untracked-files=all`，同时覆盖 tracked diff 与非忽略的
  untracked 文件。
- 三份已完成施工任务书已转为 `superseded / 历史证据`；文档守卫新增「任务 done/dropped/
  superseded 时任务书不得仍为 draft」，第 N 向反向探针可使它单独变红。
- state 的 `unknowns` 只保留当前仍未知事项；同日已经解除并由真实重跑证明的欠费事故留在计划 §9.35
  和时点证据，不再冒充当前未知。
- 当前计划不再把本地非仓库参考图和一次性探针脚本写成可恢复的仓库路径。

## 验证

- Python 语法检查：通过。
- 文档守卫：通过；登记 58/58。
- 文档反向探针：13/13 与预期一致，新增 N 向能抓住完成任务书仍为 draft。
- 项目状态守卫：通过。
- 项目状态反向探针：19/19 与预期一致。
- 完成矩阵机械汇总：证据齐备 16/17，闭合 15/17；仅 C15/C17 人工门保持开放。
- 本机未来报告污染探针：修复前选中未跟踪报告，修复后只选已跟踪报告。
- CI 副作用反向探针：新增一个非忽略的未跟踪文件后，`git status --porcelain --untracked-files=all`
  精确报告该文件；探针随后删除。

## 快照与边界

修改前快照：
`E:\workbuddy_workspace\2026-09-20-16-38-19\_stage-amz-control\cp2-pre-goal-20261001-115358`

| 文件 | 修改前 SHA-256 | 修改后 SHA-256 |
|---|---|---|
| `.gitignore` | `d39b3e39b950ed5098ec349d2f07782f0373a015d5789cf223be8e465362e80b` | `948a6f606a0778efdd00c1a85b9c6d1fa74f51933bf422111f14bee7f5ab1394` |
| `.github/workflows/ci-cd.yml` | `d791044234c4d3b9ab04e185e3e2c69468e97977f29e627edf9633c0e050cfe7` | `3752ce2386fd6b31ca24bc624ef7c7cf2b703c03388d5d5e08ab93c5f042b17c` |
| `AGENTS.md` | `6607584ffc9f1d49812b6afe2bc27a08fc9b06ac57cdc775ed4b7df3f2ef3322` | `0fc9a47b138b44b5ddd549928cbcb4276eb37d754f6ce8b2a63c5b298af9ca94` |
| `docs/INDEX.md` | `253b9adbe5070410dc81a29f84edee32bbdb975619889f639f414b1b83c3f295` | `8819643503c94f92c19d3bdcc7e7125af0bc40a6dc639d407e4b2317f5071313` |
| `docs/product-v2-goal-and-implementation-plan.md` | `e9d0434faa0512ff76fe44cb67bd592cf9f9610f89d4c8c9257ce74f153dc4c6` | `0d7d06c61ce0aafca2fa1f3c02e415eb7cbb0c2adcced91dd0d57f84ed9056ca` |
| `_working/amz-listing-kit-product-v2/state.md` | `1d6b8e1445adceb268970af61b6f9d01cc5f3dcf04e8cf1bf16d5885a5611c18` | `e83fafacf1edefe86735dee20d1904f83964fae6d338fd2c9f7fb131eb3e8466` |
| `tasks/v255-server.md` | `da42a99ba68e34279501c347d7bb46b69a164376d6a1081e6497e3bbb354b79c` | `d3227682e74e93f3bd334d51a5b54e0cabaf1c901fedcdca51653be392290d68` |
| `tasks/v255-verifier.md` | `3a5af5fa9061fc46c1c97e074d1ae9e3f3fb9d0f68d951d12111f27269eaa27f` | `c01932650294f555d4ccc78291ee6476ab34e79ca551c3c89f74967fdce1d5b6` |
| `tasks/v2ui2-interaction-visual.md` | `688d5a8ba842a5384a5891a36aee775ae634d02b049b4a1286c2de7f646a1edf` | `6b9c1f47d2417eeebf1123b1cb7ef14b24207fbf7838af34cd70a1992df8c5cc` |
| `tools/check_docs.py` | `77209a588e0b5babffe4bb76ed68a1f2745485f7348b6665600105111912bb1f` | `3bb28413a13fc63fd5a036641e395dcc2a7f6ae6d8a46a2b4827ffd3161253ba` |
| `evals/probes/docs_index.py` | `402689f11b494b58bff68f7846b5aa5a585d2c92d95bc495bb0b16c5e167fb74` | `7194e743c6c2c700a97ae7260cf645225b0bdab15da6c74687ffce9bcc6f8692` |
| `tools/audit_v2_7_4_completion.py` | `24c3ea361130e4e627230aa6bf8a8a5294245f4ffcd4626ff77daec7159e5179` | `1dd662190cfbf9ed2c3a47ee20c7a01c2a30d622b2d9275e3ff71c1fb2a5e710` |

本轮没有恢复系统 Goal，没有把 Phase 7 或 V2.7.3 改成 active，没有替代 C17 产品发起人走查或 C15
首次使用者走查。当前唯一下一动作仍为 V2.7.3；恢复时必须先改变系统 Goal 生命周期，再同步 state。
