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
