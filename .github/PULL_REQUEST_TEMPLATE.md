## changed_files
- 列出本次实际改动文件；未改动的授权文件写明“未改动”。

## patch_plan
- 用 3-8 行写清本次实际执行的改动方案，不写计划外内容。

## diff_summary
- 概括行为变化、契约变化、仅影响 review 的关键信息。

## risks
- 列出最值得 reviewer 重点检查的风险点。

## test_commands
- 按实际执行顺序列出命令。
- 先写定向测试，再写全量 `python3 -m pytest -q`。

## test_outputs
- 粘贴关键原始输出，不要只写 passed。

## validation_evidence
- 提供可核对的真实样例，例如响应头、JSON 片段、日志样例、文件校验结果。

## rollback_note
- 写最小回滚路径。

## review_checklist
- [ ] 只修改了授权文件
- [ ] 未做无关重构或无关清理
- [ ] 未新增第三方依赖，或已在工单中明确授权
- [ ] 未修改现有 API 路径
- [ ] 若改响应字段，仅新增未删除
- [ ] 已先跑定向测试，再跑全量回归

## schema_change_checklist
- [ ] 是否新增表？如果是，已补 lifecycle manifest entry / owner / business key / PII level。
- [ ] 是否删除表？如果是，已说明 replacement / retired lifecycle / rollback note。
- [ ] 是否变更业务主键？如果是，已说明迁移路径、回填策略、读写路径影响。
- [ ] 是否影响 unionid？如果是，已覆盖身份解析、历史数据、幂等和回滚验证。
- [ ] 是否影响 external effect？如果是，已确认真实外呼边界、审计、重试和发送人约束。
- [ ] 是否影响 payment / notification？如果是，已确认支付状态、通知幂等和回调兼容性。
- [ ] 是否影响 material assets？如果是，已确认素材 lineage、usage、分页和校验规则。
- [ ] 如涉及 migration，已按 `docs/development/schema_migration_template.md` 填写迁移头和验证证据。
