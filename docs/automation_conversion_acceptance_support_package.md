# 自动化转化验收支持包

本目录下与业务验收直接相关的交付物如下：

- `docs/automation_conversion_business_acceptance.md`
  - 业务目标、6 池子定义、普通/重点完整链路、OpenClaw 与人工边界、v1 限制
- `docs/automation_conversion_local_runbook.md`
  - 本地启动、配置、seed、联调路径、curl 示例
- `docs/automation_conversion_acceptance_checklist.md`
  - 验收 checklist
- `docs/automation_conversion_config_matrix.md`
  - 配置项矩阵
- `docs/automation_conversion_open_issues.md`
  - 当前已知 open issues
- `scripts/seed_automation_conversion_demo.py`
  - 本地 demo 客户与联调配置 seed 脚本

建议业务验收顺序：

1. 先看 `automation_conversion_business_acceptance.md`
2. 再看 `automation_conversion_config_matrix.md`
3. 按 `automation_conversion_local_runbook.md` 跑本地联调
4. 用 `automation_conversion_acceptance_checklist.md` 勾验收项
5. 验收过程中碰到边界问题时，回看 `automation_conversion_open_issues.md`
