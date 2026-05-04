# UI Redesign PR Notes

## 背景

本次改动目标是把当前仓库真实会落到前端的 admin / questionnaire h5 / sidebar 页面，统一重做成用户提供 zip 所定义的设计语言，同时保持：

- 业务逻辑不变
- 接口语义不变
- 路由语义不变
- 数据模型不变
- automation_program Phase 1 结构不被破坏
- SSO / RBAC 主逻辑不被破坏

## 设计来源

- `/Users/qianlan/Downloads/AIcrm _.zip`
- 核心 token 来源于 `redesigned/admin_console.css`
- 问卷 H5 直接参考 `redesigned/questionnaire_h5_page.html`、`redesigned/questionnaire_h5_submitted.html`、`redesigned/open_in_wechat.html`
- 侧边栏直接参考 `redesigned/sidebar_bind_mobile.html`

## 本次改造范围

### 后台公共壳层

- admin 公共蓝灰 design system
- login / api docs / placeholder 首屏重构
- program context header
- config 公共壳层

### 自动化运营

- 方案列表页改成 Hero + summary cards + table/list
- program 内 overview / operations / workflow editor / nodes / executions
- flow-design / member-ops
- shared / runtime 风格统一

### 配置中心

- 统一成“列表 + 编辑区 / 抽屉”的后台模式
- `login-access` 明确表达为企微成员授权页

### 问卷

- 问卷后台列表、编辑、结果页统一到蓝灰内容管理风格
- 问卷 H5 与提交成功页按 zip 的移动端风格重做
- “请在微信内打开”页按 zip 的阻断态重做

### 侧边栏

- bind-mobile 页以及当前实际渲染的单客户操作卡片改成 zip 的 sidebar 风格
- 保留所有 `data-*` URL、DOM id、JSSDK 与动作接口绑定

## 结构性约束

- 所有 UI 改动优先通过模板重排和 CSS override 完成。
- 旧文案里被测试依赖的关键字符串保留：
  - `企业微信登录`
  - `API 文档`
  - `登录与权限`
  - `自动化运营方案列表`
  - `默认自动化转化方案`
  - `新建方案`
  - `问卷管理`
  - `返回问卷管理`
  - `请在微信客户端打开`
  - `立即授权并填写`
  - `已经提交`
  - `客户档案绑定`
  - `第一阶段保留 自动化运营、客户、问卷、配置、API 文档`
- H5 表单关键 DOM 保持不变：
  - `id="questionnaire-form"`
  - `method="post"`
  - `action="/api/h5/questionnaires/<slug>/submit"`
- sidebar 关键 `data-*` API URL 保持不变。

## 路由口径说明

- 真实执行记录页当前 route 是 `/admin/automation-conversion/programs/<id>/executions`。
- 旧全局入口 `/admin/automation-conversion/operations/executions` 已下线；真实执行记录页当前 route 是 `/admin/automation-conversion/programs/<id>/executions`。
- `/s/<slug>` 会按环境分支渲染：
  - 问卷授权门页
  - 问卷填写页
  - 非微信提示页

## 验证目标

- 后台主要页面打开不报错
- H5 主要页面打开不报错
- sidebar 主要页面打开不报错
- 主要 CTA、筛选、表单提交、workflow / node / execution 页面 JS 初始化不被 UI 改造打坏

## 交付文档

- `docs/ui_redesign_inventory.md`
- `docs/ui_redesign_design_system.md`
- `docs/ui_redesign_page_specs.md`
- `docs/ui_redesign_pr.md`
