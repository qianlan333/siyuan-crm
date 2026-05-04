# Blueprint Conflict Cleanup

日期：2026-04-17

状态：Completed in Wave 1 Preflight

## 1. 检查范围

本次检查目标：

- 仓库中是否同时存在新版与旧版《AI-CRM 全局重构蓝图 V1》
- 是否存在多个可被误认为“当前正式蓝图”的同名或近似命名文件

执行范围：

- 全仓库 Markdown 文档
- 关键词：
  - `AI-CRM 全局重构蓝图 V1`
  - `platform-refactor-blueprint-v1`
  - `重构蓝图`

## 2. 检查结果

当前只发现 1 份正式蓝图文件：

- `docs/architecture/2026-04-17-platform-refactor-blueprint-v1.md`

当前审阅与执行均必须以这 1 份文件为唯一有效基线。

本次未发现：

- 另一个同名旧版 `AI-CRM 全局重构蓝图 V1`
- 另一个 `platform-refactor-blueprint-v1` 变体
- 需要删除、归档或标记 `OBSOLETE` 的重复蓝图副本
- 同时存在“第 11 节先拆大模块”和“Wave 1 先收口入口”两套并行有效版本

## 3. 本次清理动作

由于没有发现重复蓝图副本，本次没有执行：

- 删除旧文件
- 移动到 `archive/`
- 增加 `OBSOLETE` 文件头

本次实际执行的清理动作只有一项：

- 修正了正式蓝图内部的顺序冲突，明确：
  - Wave 1 先收口入口
  - 大模块拆分进入 Wave 2 及之后

## 4. Canonical 口径

从本次 preflight 起，唯一正式蓝图口径固定为：

- `docs/architecture/2026-04-17-platform-refactor-blueprint-v1.md`

以下类型文档不视为“蓝图副本”：

- `docs/plans/*`
- 各专题审计 / 设计 / runbook
- `docs/refactor/*` 下的执行文档

它们可以引用正式蓝图，但不得替代正式蓝图。

## 5. 后续规则

后续如果再新增新的平台级蓝图版本，必须满足：

1. 新旧版本文件名显式区分
2. 旧版本文件头标记 `OBSOLETE` 或移动到 `archive/`
3. 在本文件追加一条清理记录
