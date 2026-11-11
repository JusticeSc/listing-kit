# amz-listing-kit Product V2 项目上下文

> CONTROL-STATUS: current · AUTHORITY: project-context
> 本文件回答“项目是什么、怎样运行、数据归谁、目录与质量门槛是什么”。产品目标、验收与任务图只在
> [`product-v2-refactor-plan.md`](product-v2-refactor-plan.md) 维护；执行位置只在
> [`../_working/amz-listing-kit-product-v2/state.md`](../_working/amz-listing-kit-product-v2/state.md) 维护。

按职责选择运行与所有权、技术选型、依赖登记或质量门槛。下列主题入口保留原章节编号；选型与依赖表按行续接，前后片导航可顺序读完完整登记。

## 任务导航

- [身份、来源、运行与所有权](product-v2-project-context.runtime.md)
- [技术栈与选型 SEL-000–009](product-v2-project-context.technology-selection-000-009.md)
- [选型 SEL-010–018](product-v2-project-context.selection-010-018.md)
- [选型 SEL-019–025 与结论边界](product-v2-project-context.selection-019-025.md)
- [Python 依赖与开发环境](product-v2-project-context.dependencies-python.md)
- [前端依赖：类型、生成器与平台包](product-v2-project-context.dependencies-frontend-core.md)
- [前端依赖：工具与运行库](product-v2-project-context.dependencies-frontend-tools.md)
- [vendor、目录与模块职责](product-v2-project-context.vendor-and-module-map.md)
- [不变约束、质量与上下文路由](product-v2-project-context.quality-and-routing.md)

## 1. 项目身份

查看项目使用者、核心任务、价值与平台边界。见 [身份、来源、运行与所有权](product-v2-project-context.runtime.md)。

## 2. 迁移基线与事实来源

区分 V1 历史、V2 实现、参考模板及各自事实来源。见 [身份、来源、运行与所有权](product-v2-project-context.runtime.md)。

## 3. 运行边界与数据所有权

查看浏览器、Python 网关和外部模型之间的数据流。见 [身份、来源、运行与所有权](product-v2-project-context.runtime.md)。

### 3.1 权威状态

定位项目、指针、执行、备份与人工采用的权威。见 [身份、来源、运行与所有权](product-v2-project-context.runtime.md)。

### 3.2 无状态的准确边界

理解无业务状态、请求日志和 Unknown 的边界。见 [身份、来源、运行与所有权](product-v2-project-context.runtime.md)。

### 3.3 运行与部署取值

查看端口、宿主、Docker、发布、TLS 与密钥来源。见 [身份、来源、运行与所有权](product-v2-project-context.runtime.md)。

## 4. 技术栈与可替换边界

查看当前技术层、可替换边界与 Provider 装配。见 [技术栈与选型 SEL-000–009](product-v2-project-context.technology-selection-000-009.md)。

### 4.1 选型记录

完整选型表按原顺序分为三片；原表列名与 SEL 行完整保留：

- [技术栈与选型 SEL-000–009](product-v2-project-context.technology-selection-000-009.md)
- [选型 SEL-010–018](product-v2-project-context.selection-010-018.md)
- [选型 SEL-019–025 与结论边界](product-v2-project-context.selection-019-025.md)

### 4.2 依赖与 vendor 登记

依赖与 vendor 的标记、登记行、版本、许可和移除成本保留在以下正文：

- [Python 依赖与开发环境](product-v2-project-context.dependencies-python.md)
- [前端依赖：类型、生成器与平台包](product-v2-project-context.dependencies-frontend-core.md)
- [前端依赖：工具与运行库](product-v2-project-context.dependencies-frontend-tools.md)
- [vendor、目录与模块职责](product-v2-project-context.vendor-and-module-map.md)

## 5. 目标目录地图

定位当前目标目录与保留材料。见 [vendor、目录与模块职责](product-v2-project-context.vendor-and-module-map.md)。

### 5.1 业务模块与承接边界

查看业务职责、现有落点与所有权承接边界。见 [vendor、目录与模块职责](product-v2-project-context.vendor-and-module-map.md)。

## 6. 不变约束

查看事实、版本、返工、Unknown、安全与界面的不变约束。见 [不变约束、质量与上下文路由](product-v2-project-context.quality-and-routing.md)。

## 7. 质量门槛

查看控制面、领域、服务、浏览器、生成、静态检查与交付各自所需证据。见 [不变约束、质量与上下文路由](product-v2-project-context.quality-and-routing.md)。

## 8. 上下文读取与写入路由

进入 INDEX 的恢复读取顺序与写入路由。见 [不变约束、质量与上下文路由](product-v2-project-context.quality-and-routing.md)。

