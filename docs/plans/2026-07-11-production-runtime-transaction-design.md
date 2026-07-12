# AI-CRM 生产运行时事务化设计

## 问题定义

2026-07-11 生产事故不是单一密钥缺失，而是发布流程没有把代码、数据库、环境文件和 systemd 运行单元视为同一个事务：Secret 已迁移为 `secretref`，但未受管的 approval timer 在迁移窗口通过 `Requires=` 拉起 Web，Web 因而继承旧环境；随后 Secret 对账失败，发布退出，却没有把半启动的运行时收回。旧 timer、错误运行用户和仓库外 unit 又让该状态长期漂移。

同时，生产已运行 `AI-CRM-ID-refactor@970da6c`，而规范仓库 `qianlan333/AI-CRM` 尚未包含这组安全基线。AI-CRM 若直接发布当前 main，会回退到不完整的 Secret 读取与部署逻辑。因此 AI-CRM 必须先吸收线上基线，再成为唯一发布源。

## 方案选择

采用“声明式运行单元 + 发布事务”方案：

1. 将 `AI-CRM-ID-refactor/main@970da6c` 合入 AI-CRM 当前 main，保留 AI-CRM 后续手机号校验和 callback overlay 退场改动。
2. GitHub workflow 与生产主机双层互斥；跨仓库旧 publisher 必须在首次正式切换前停用，因为仅由新 workflow 遵守的 advisory lock 不能约束旧发布脚本。
3. release bundle 只读校验后、任何 stash/reset 之前，从目标 release 解出 runtime controller，安装 systemd `ConditionPathExists` 持久闸门并静默所有 active/approval timer、对应 service 与 Web。
4. Secret 对账后只通过 `/run` 授权放行 primary Web，timer/worker 仍受 deploy-in-progress 阻断；Web canary 通过后再用第二个 `/run` 授权临时放行其余 runtime。运行单元对账和公网 exact-SHA 全部通过后，最后删除运行时授权与持久闸门并立即提交事务。任一步失败，EXIT trap 重新创建持久闸门并停止 Web/managed timer；硬重启会清空 `/run` 授权，不能绕过未提交事务。
5. `production_runtime_units.json` 是 systemd desired state：active、approval-required、retired 必须互斥且穷尽。approval timer 在迁移时停止，成功后只恢复原本 enabled 的 timer；retired timer/service 强制 disable、stop、reset-failed。
6. 所有读取 `/home/ubuntu/.openclaw-wecom-pg.env` 的受管 service 必须以 `ubuntu` 运行，且 ExecStart 指向仓库内真实脚本/module。Web unit 在启动前必须从当前 release 安装并 enable；重复的 `aicrm-web.service` 必须退役，不能留下两个 5001 进程定义。

## 安全与边界

- capability owner：`platform_ops / production_runtime`。
- 涉及既有 Next routes：`/health`、`/auth/wecom/start`；不新增业务 route。
- canary 只验证本地 302 外层官方域名、身份参数和内层公网 callback URL，不跟随跳转，不触发企微 token 交换或其他真实外呼。
- 不写业务生产数据；只有既有 Alembic、Secret migration 和 systemd desired-state 操作。
- fixture/local-contract 结果不作为生产证据；合并后必须验证公网 release SHA 与真实 systemd 状态。
- rollback 为上一支持 `secretref` 的 release；一旦 mutation 开始，失败默认 fail-closed，不回退到不认识 `secretref` 的旧版本。

## 验收标准

- 同一生产主机不能同时运行两个 deploy transaction。
- migration 窗口内 active/approval timer 与 Web 全部停止。
- Secret 对账失败时持久 deploy guard 保留、Web 保持停止，主机重启后也不能返回 200。
- `aicrm-archive-sync.service` 以 `ubuntu` 运行并能解析 Secret Store。
- reply-monitor、旧 automation jobs、旧 campaign timer 和孤儿 conversion service 不再 active/enabled/failed。
- Web 启动后 `/health` 的关键 Secret 状态为真，企微两种登录 start 均 302 到官方域名且未执行真实外呼。
- CI 能在 unit 缺 User、入口脚本不存在、manifest 漏分类、workflow 缺锁或缺 fail-closed trap 时失败。
