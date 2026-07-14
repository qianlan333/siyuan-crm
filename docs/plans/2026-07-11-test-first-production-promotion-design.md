# 测试优先与人工生产晋级设计

## 目标

所有 `main` 自动发布只允许进入测试服务器 `49.232.57.128`。正式服务器
`150.158.82.186` 不再接受 `workflow_run`、`push`、定时任务或仓库 webhook
触发的自动发布；只有人工选择已在测试环境验证过的精确提交，并通过 GitHub
`production` environment 审批后，才能晋级正式环境。

## 方案选择

采用“自动测试部署 + 独立人工生产晋级”。仅切换 `DEPLOY_HOST` 会继续复用生产
密钥，并在测试机执行生产域名 Nginx 收口，无法满足环境隔离。完全关闭发布虽然
安全，但会失去持续测试环境。拆分后的两条链路使用不同 secret scope、不同触发器
和不同公网验收域名，既保持测试自动化，又让正式发布必须经过人工动作。

## 发布链路

1. `main` 的 `CI Fast` 成功后，`Deploy to Test` 自动构建并校验 exact-SHA bundle。
2. bundle 只能使用仓库级 `TEST_DEPLOY_*` secrets 传到 `49.232.57.128`。
3. 远端完成迁移、服务重启、本机 exact-SHA、后台页面、callback 与 runtime-unit
   验收后，只读取 `https://id-dev.youcangogogo.com/health` 验证公网 SHA；不得运行
   生产域名 Nginx 修改器。
4. `Promote to Production` 只支持 `workflow_dispatch`。操作者必须输入 40 位
   `release_sha` 和固定确认语；workflow 先证明测试公网已经运行同一 SHA。
5. 正式 job 使用受 required-reviewer 保护的 `production` environment secrets，
   再执行原有生产迁移、服务与 `www.youcangogogo.com` exact-SHA 收口。

## 安全与失败处理

- 自动 workflow 不可引用 `DEPLOY_HOST`、`DEPLOY_USER`、`DEPLOY_SSH_KEY`。
- 人工生产 workflow 不可包含 `workflow_run`、`push` 或 `schedule`。
- 测试 SHA 不一致、提交不是 `main` 历史、确认语错误或 environment 未批准时，
  正式发布必须在传输和远端写入前失败。
- 测试发布失败不回退到 150；正式发布回滚只允许人工晋级上一已验证 SHA。
- 原 `qianlan333/AI-CRM` 自动生产 workflow 保持禁用，避免另一仓库覆盖正式机。

## 验收

- workflow contract 测试证明触发器、secret scope、目标域名和人工门禁。
- YAML 可解析，架构门禁通过。
- 合并后重新启用测试 workflow，49 的 `/health` 返回合并 SHA。
- 150 的 `/health` 在测试自动发布前后保持原 SHA。
