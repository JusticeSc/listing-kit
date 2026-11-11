# amz-listing-kit

> CONTROL-STATUS: current · AUTHORITY: implemented-behavior
> 本文件只回答“当前代码实际能做什么、怎样启动和验证”。产品目标见
> [`docs/product-v2-refactor-plan.md`](docs/product-v2-refactor-plan.md)，
> 当前进度与下一动作见
> [`_working/amz-listing-kit-product-v2/state.md`](_working/amz-listing-kit-product-v2/state.md)，
> 文档身份和读取顺序见 [`docs/INDEX.md`](docs/INDEX.md)。

只读冷恢复入口：`uv run --locked python tools/refactor_resume.py`。它核对仓库计划、状态与观察证据，
输出下一任务及可读 Goal；显示的是仓库保存的最近观察，不会查询系统 Goal。恢复会话须另读真实 Goal，
不能把历史观察当当前读数。当前原产品终点/停工及main基线规划边界只见计划§2.1/§17.13，绑定与历史计数只看state；main现有能力的清理/依赖替换计划取#10/#7，封存下一版WIP不算当前实现。规划完成不是产品验收或恢复施工。

按任务阅读以下分片；当前能力、启动要求与验证边界均保留在对应正文中。本页保留原主题入口，正文中的状态与证据归属仍按原文读取。

## 任务导航

- [当前能力与实现边界](README.behavior.md)
- [启动、模型设置与运行链](README.startup.md)
- [验证、交付、目录与安全](README.validation-and-delivery.md)

## 当前可用边界

查看当前项目、事实、套图、Prompt、生成、复核、采用与导出的实际能力及未验边界。见 [当前能力与实现边界](README.behavior.md)。

## 启动

查看环境、依赖安装、构建、启动、HTTPS、模型设置与凭据。见 [启动、模型设置与运行链](README.startup.md)。

## 实际运行链

查看 Python 路由、浏览器 Module、存储和导入的实际运行关系。见 [启动、模型设置与运行链](README.startup.md)。

## 验证当前实现

选择当前实现的验证入口，分清离线、真实调用与远程检查。见 [验证、交付、目录与安全](README.validation-and-delivery.md)。

## CI/CD

查看 CI/CD 触发、发布事务、回退和实际上线证据的边界。见 [验证、交付、目录与安全](README.validation-and-delivery.md)。

## 已退役入口（P1 随 main 基线退出仓库）

查看已删除的 V1/Mock 参数与历史追溯入口。见 [验证、交付、目录与安全](README.validation-and-delivery.md)。

## 代码地图

定位当前正式入口、前端、Provider、配置和工具。见 [验证、交付、目录与安全](README.validation-and-delivery.md)。

## 配置与安全边界

查看监听、无服务器项目库、浏览器数据恢复与环境变量边界。见 [验证、交付、目录与安全](README.validation-and-delivery.md)。

