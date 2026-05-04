# CRM Inventory Corrections

## 这轮为什么要纠偏

上一版 CRM inventory 的主要问题不是“接口一定写错了”，而是“现状、规划、推测”混在了一起，缺少足够的来源证据。

这会带来两个直接风险：

- 后续改 `customer_center` / `customer_timeline` 时，开发者可能把“文档里出现过”误认为“接口已经落地”
- questionnaire、admin、callback 这些边界复杂的路由，如果没有真实 handler 证据，后面很容易继续靠猜

## 上一版有哪些地方需要纠偏

### 1. Current inventory 没有严格区分“已实现”和“未来规划”

上一版 route inventory 把所有路由放在一个大表里，虽然大部分都是真实存在的，但读者很难分辨：

- 这是代码里已经注册到 Flask 的路由
- 还是后续 CRM 改造时可能会用到的概念接口

这次已经拆成：

- `Current Implemented Routes`
- `Planned / Reserved Routes`

并且 `Current Implemented Routes` 只接受代码和 `url_map` 双重校验。

### 2. 缺少来源证据，容易把猜测写成现状

上一版每条路由没有写 handler 来源，导致后续很难判断：

- 是真实存在的 Flask endpoint
- 还是文档整理时按命名习惯补上的“合理猜测”

这次每条当前已实现路由都补了来源证据：

- `routes.py:行号 + handler 名`
- `url_map endpoint=...`

这样后续有人质疑某条路由时，可以直接反查代码。

### 3. questionnaire 路由之前容易被“泛化理解”

问卷相关路由之前容易被笼统写成：

- questionnaire public
- questionnaire admin

但实际上当前代码已经分成了几类不同入口：

- slug 页：`/s/<slug>`、`/s/<slug>/submitted`
- H5 API：`/api/h5/questionnaires/<slug>`、`/api/h5/questionnaires/<slug>/submit`
- OAuth：`/api/h5/wechat/oauth/start`、`/api/h5/wechat/oauth/callback`
- admin API：`/api/admin/questionnaires*`
- admin UI：`/admin/questionnaires/ui`

这次已经按真实 path 全部拆开，不再用泛化描述替代真实路由。

## 这轮如何校正

本次采用两层校验：

1. 运行时校验  
   通过 `create_app().url_map.iter_rules()` 导出当前实际注册路由。

2. 源码校验  
   通过扫描 `@bp.route(...)` 装饰器，补充 handler 名和行号。

这意味着：

- 文档里出现的“当前已实现路由”，都能在运行时找到
- 文档里每条现有路由，都能回到具体 handler

## 对后续 customer_center / customer_timeline 的意义

这轮纠偏的意义不是新增功能，而是建立一个可信边界：

- 后续改 `customer_center` 时，能明确哪些是它已经依赖的现有输入接口
- 后续改 `customer_timeline` 时，能明确哪些消息、群、问卷、class_user 路由是真实来源
- 后续补 internal auth 时，能区分“当前真实存在的敏感接口”与“未来新增后需要保护的接口”

简化成一句话：

- 这轮把 CRM 路由清单从“经验性文档”改成了“可回到代码和 url_map 的护栏文档”。
