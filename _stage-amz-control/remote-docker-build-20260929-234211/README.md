# amz-listing-kit

> CONTROL-STATUS: current · AUTHORITY: implemented-behavior
> 本文件只回答“当前代码实际能做什么、怎样启动和验证”。产品目标见
> [`docs/product-v2-goal-and-implementation-plan.md`](docs/product-v2-goal-and-implementation-plan.md)，
> 当前进度与下一动作见
> [`_working/amz-listing-kit-product-v2/state.md`](_working/amz-listing-kit-product-v2/state.md)，
> 文档身份和读取顺序见 [`docs/INDEX.md`](docs/INDEX.md)。

## 当前可用边界

默认入口现在提供 Product V2 的浏览器本地项目外壳：

- 从空白页面新建、打开、重命名、复制和删除项目；
- 项目列表和业务对象保存在当前浏览器的 IndexedDB；
- localStorage 只保存当前项目指针；
- 将完整项目导出为 ZIP，或从 ZIP 导入；导入前校验结构和内容哈希；
- Python 服务只提供静态页面和健康检查，不保存工作空间、最近项目或图片。

当前默认页面**还不能**录入商品资料、调用语义模型、规划套图、生成图片、审核返工或导出交付套图。
这些是 Product V2 的后续能力，不能因为旧 Product V1 已实现过就声称当前入口也已具备。

## 启动

环境要求：Python 3.13、现代桌面浏览器；依赖锁定在 `requirements.txt`。

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app\server.py --check
.venv\Scripts\python.exe app\server.py --open
```

默认地址为 `http://127.0.0.1:8780/`。若需要让内网或穿透工具访问，可显式设置监听地址；暴露范围和访问控制由运行者负责：

```powershell
.venv\Scripts\python.exe app\server.py --host 0.0.0.0 --port 8780
```

默认 Product V2 不需要模型密钥，因为模型 API 尚未接入正式入口。密钥只允许通过服务器环境变量提供，
不得写进浏览器、项目包、日志或 Git。

## 实际运行链

```text
app/server.py
  → app/product_v2_server.py
      ├─ GET /、/index.html、静态资源
      ├─ GET /api/health
      └─ 其他 /api/* 与全部 POST：404

浏览器 app/product_v2/app.js
  → storage/repository.js
      ├─ IndexedDB：项目、对象、Blob、版本
      └─ localStorage：当前项目 ID
```

页面不会读取服务器文件夹，也没有 `directory`、workspace 或 recent-workspaces 参数。项目导入先在内存中校验，
成功后才写入浏览器数据库；同 ID 项目会作为新项目导入，不覆盖既有项目。

## 验证当前实现

以下入口分别验证正式服务、浏览器存储、项目首页、项目包和领域合同：

```powershell
python app\server.py --check
uv run --no-project --with-requirements requirements.txt --with playwright python tools\verify_v2_1_1_indexeddb.py
uv run --no-project --with-requirements requirements.txt --with playwright python tools\verify_v2_1_2_project_home.py
uv run --no-project --with-requirements requirements.txt --with playwright python tools\verify_v2_1_3_project_package.py
uv run --no-project --with-requirements requirements.txt --with playwright python tools\verify_v2_1_4_formal_entry.py
uv run --no-project --with-requirements requirements.txt --with playwright python tools\verify_v2_2_1_product_contracts.py
```

文档、状态和控制面守卫必须串行执行：

```powershell
uv run --no-project --with-requirements requirements.txt python tools\check_docs.py --no-run
uv run --no-project --with-requirements requirements.txt python tools\check_project_state.py
uv run --no-project --with-requirements requirements.txt python evals\probes\project_state.py
```

`--no-run` 只检查文档结构与登记关系，不证明 README 中的命令已执行。产品完成声明还需要浏览器、
IndexedDB、API、真实 Provider 和首次使用者证据，具体门槛由产品计划定义。

## CI/CD

`.github/workflows/ci-cd.yml` 在 PR 和 push 上执行控制面守卫、当前 Product V2 浏览器验证、Docker 构建和
容器健康检查。本机不承担正式容器运行。只有 `main` push 会部署：Actions 使用仓库中的 `SSH_HOST`、
`SSH_USER`、`SSH_PRIVATE_KEY`，把以 Git SHA 标记的镜像传到远程服务器，再由远程 Docker 替换同名容器。
新容器健康失败时恢复上一容器；PR 不部署。服务器可选将运行时变量放在
`$HOME/.config/amz-listing-kit/app.env`。

这套流程存在不等于已经部署成功；是否真实上线必须以对应的 GitHub Actions run 和目标机
`GET /api/health` 为证据。

## 历史 Product V1

旧 Product V1 仍作为回归基线保留，拥有服务器文件夹工作空间、商品资料、提示词、真实图片生成、候选、
单图返工、人工选择和导出等能力。它的状态所有权与 Product V2 不同，不是默认产品入口：

```powershell
python app\server.py --legacy-v1 --check
python app\server.py --legacy-v1 --open
python tools\regress_product_v1.py
```

旧离线 Mock 只用于历史状态轨迹回归：

```powershell
python app\server.py --offline-fixture demo\fixture\aster-01 --check
```

Product V1 的设计和完成轨迹已登记为 `superseded`；需要追溯时从 `docs/INDEX.md` 进入，不把固定七坑位、
服务器工作空间或抠图路线重新带回 Product V2。

## 代码地图

```text
app/server.py                    正式启动入口；默认 V2
app/product_v2_server.py         V2 无状态 HTTP 适配器
app/product_v2/                  V2 页面、领域合同与 IndexedDB 存储
src/providers/                   Provider 适配器；未提交草案不算当前实现
config/product-v2/               V2 配置目标目录；未提交内容不算当前实现
tools/                           自检、契约验证和控制面守卫
evals/product-v2/                时点证据，不是当前状态或规范
docs/INDEX.md                    文档身份与读写路由
```

## 配置与安全边界

- 当前默认服务绑定 `127.0.0.1`；是否经内网穿透暴露由运行者决定。
- Product V2 服务端没有账户、租户、数据库或用户项目索引。
- `DASHSCOPE_API_KEY`、`SEMANTIC_MODEL`、`IMAGE_MODEL` 等只从服务端环境变量读取。
- 浏览器站点数据被清理或 origin 改变时，只能通过此前导出的项目 ZIP 恢复。
- 工作区中未被 Git 跟踪的 provider/config 文件属于候选实现，不应写进“已实现”说明。
