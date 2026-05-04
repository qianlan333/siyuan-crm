# automation_program Phase 1 UAT

## 1. 方案列表

### 操作步骤
- 登录后台，进入 `/admin/automation-conversion`
- 观察页面标题、说明文案和卡片列表
- 在页面顶部点击“共享资源”“运行时中心”
- 在方案列表行上查看“编辑 / 停用 / 复制 / 归档”等按钮

### 预期结果
- 页面标题为“自动化运营方案”
- 页面主体是方案列表，不再直接进入旧单例 overview
- 页面上可见“新建方案”“编辑”“复制”“启用/停用”“归档”
- 顶层一级导航仍只保留：自动化运营、问卷、配置、API 文档

## 2. 默认方案

### 操作步骤
- 在方案列表页找到默认方案卡片
- 记录默认方案的 code、name、status
- 点击“编辑”

### 预期结果
- 默认方案存在
- `program_code = signup_conversion_v1`
- `program_name = 默认自动化转化方案`
- 默认状态为 `active`
- 点击“编辑”后跳转到默认方案 overview，而不是旧单例页

## 3. 方案内页面

### 操作步骤
- 分别访问：
  - `/admin/automation-conversion/programs/<default_program_id>/overview`
  - `/admin/automation-conversion/programs/<default_program_id>/operations`
  - `/admin/automation-conversion/programs/<default_program_id>/flow-design`
  - `/admin/automation-conversion/programs/<default_program_id>/member-ops`
  - `/admin/automation-conversion/programs/<default_program_id>/executions`
- 检查每个页面顶部 program context

### 预期结果
- 每个页面都能正常打开
- 每个页面顶部都能看到方案名、方案状态、返回方案列表
- 方案内 tabs 只围绕当前 program 工作面，不混入 shared/runtime

## 4. 旧入口下线校验

### 操作步骤
- 依次访问：
  - `/admin/automation-conversion/overview`
  - `/admin/automation-conversion/operations`
  - `/admin/automation-conversion/flow-design`
  - `/admin/automation-conversion/member-ops`

### 预期结果
- 所有旧入口均已下线，不再注册
- 当前页面从 `/admin/automation-conversion/programs/<program_id>/overview`
  `/admin/automation-conversion/programs/<program_id>/operations`
  `/admin/automation-conversion/programs/<program_id>/flow-design`
  `/admin/automation-conversion/programs/<program_id>/member-ops` 访问
- 不再直接渲染旧单例工作面
- workflow / executions 旧深层入口已下线，当前使用 `/admin/automation-conversion/programs/<default_program_id>/operations/workflows/*` 和 `/admin/automation-conversion/programs/<default_program_id>/executions`

## 5. 共享资源入口

### 操作步骤
- 访问：
  - `/admin/automation-conversion/shared/agents`
  - `/admin/automation-conversion/shared/profile-segments`
  - `/admin/automation-conversion/shared/model-infra`
- 不再访问旧 `/admin/automation-conversion/agent-config`，当前只使用 `/admin/automation-conversion/shared/agents`

### 预期结果
- shared 路由都能打开
- 旧 `agent-config` 入口已下线，不再作为可用页面入口
- shared 页面不显示 program context，不被误塞进某个方案页

## 6. 模块运行时入口

### 操作步骤
- 访问：
  - `/admin/automation-conversion/runtime`
  - `/admin/automation-conversion/runtime/sync`
  - `/admin/automation-conversion/runtime/router`
  - `/admin/automation-conversion/runtime/logs`
  - `/admin/automation-conversion/runtime/debug`
- 不再访问旧 `/admin/automation-conversion/run-center`，当前只使用 `/admin/automation-conversion/runtime`

### 预期结果
- runtime 路由都能打开
- 旧 `run-center` 入口已下线，不再作为可用页面入口
- runtime 页面保持模块级，不显示 program context

## 7. workflow / execution program 化

### 操作步骤
- 在默认方案中查看 workflow 列表
- 新建一个 workflow，并记录其 `program_id`
- 新建一个空白方案，再进入该方案查看 workflow 列表
- 在两个方案中分别查看 executions 列表
- 核查历史 workflow / execution 数据的 `program_id`

### 预期结果
- 默认方案只展示默认方案下的 workflow
- 新建 workflow 时写入当前方案 `program_id`
- 非默认方案的 workflow 列表与默认方案隔离
- execution 列表按 `program_id` 过滤
- 历史 workflow / execution 已 backfill 到默认方案

## 8. 回滚点

### 操作步骤
- 确认是否已记录本次 schema 变化与默认方案 bootstrap
- 确认回滚预案不依赖已下线旧入口
- 确认 `/admin/automation-conversion/*` 旧 route 不会被重新注册

### 预期结果
- 回滚时至少可恢复到方案列表和 program-scoped 入口可用
- 旧入口不作为回滚路径，不再提供重定向
- 默认方案数据不会丢失，最多只回退展示层与 program 过滤逻辑

## 9. 方案列表 UI polish 与基础信息编辑

### 操作步骤
- 登录后台，进入 `/admin/automation-conversion`
- 确认右上角动作区依次显示“共享资源”“运行时中心”“新建方案”
- 确认页面首屏不再默认展开完整“新建方案”表单
- 点击“新建方案”，确认表单在折叠区域展开
- 在默认方案行点击“编辑”，确认进入默认方案 overview
- 进入默认方案 overview，检查 program context header

### 预期结果
- 方案列表页保持“方案入口 + 管理列表”心智
- 新建方案入口从页面中部大表单移到右上角主按钮
- 方案列表中每行只有一个主入口“编辑”，不再同时展示“进入”和单独“编辑”
- 方案名称和说明保存后，在列表页和方案内 header 同步展示新值
- program context header 提供“编辑方案信息”入口，并保留复制、启用或停用、归档等操作
