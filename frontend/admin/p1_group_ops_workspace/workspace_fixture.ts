import { type BusinessClosurePayload, type ScenarioEvidence } from "../shared/status_model.js";

export interface WorkspaceListItem {
  id: string;
  label: string;
  kind: "plan" | "group" | "node" | "execution" | "push_center" | "evidence";
  status: ScenarioEvidence["status"];
  summary: string;
  detailId: string;
  entityType: WorkspaceEntityType;
}

export type WorkspaceEntityType = "plan" | "group" | "node" | "execution" | "push_center" | "evidence";

export interface WorkspaceDetailField {
  label: string;
  value: string;
}

export interface WorkspaceDetailItem {
  id: string;
  entityType: WorkspaceEntityType;
  title: string;
  status: ScenarioEvidence["status"];
  evidenceStatus: string;
  derivedStatus: string;
  summary: string;
  guardrail: string;
  fields: WorkspaceDetailField[];
}

export interface WorkspaceSelectionState {
  selectedPlanId: string;
  selectedGroupId: string;
  selectedNodeId: string;
  selectedExecutionId: string;
  selectedPushCenterJobId: string;
  selectedEntityType: WorkspaceEntityType;
}

export interface WorkspaceFixture {
  payload: BusinessClosurePayload;
  leftRailItems: WorkspaceListItem[];
  detailItems: WorkspaceDetailItem[];
  defaultSelection: WorkspaceSelectionState;
  workspaceMode: "draft_only_preview_only";
  dataSourceLabel: string;
  dataBindingStatus: "fixture_fallback" | "real_data_bound" | "real_data_unavailable";
  realExternalCallExecuted: false;
  productionWriteExecuted: false;
}

export const GROUP_OPS_WORKSPACE_SCENARIOS: ScenarioEvidence[] = [
  {
    key: "group_ops",
    title: "发送链路 evidence",
    status: "sent",
    evidenceStatus: "EVIDENCE_COLLECTED",
    derivedStatus: "external_effect_job_97_sent",
    summary: "Group Ops 真实发送 evidence 已成立，Push Center 显示 sent；这不代表 governance 完整。",
    guardrail: "sent evidence 只能证明发送链路，不允许跳过 approval / allowlist / gray-window。",
    route: "/admin/push-center"
  },
  {
    key: "group_ops",
    title: "治理证据",
    status: "governance-missing",
    evidenceStatus: "EVIDENCE_COLLECTED",
    derivedStatus: "approval_allowlist_window_missing",
    summary: "独立 operator approval、receiver allowlist、gray-window 记录仍未 attach。",
    guardrail: "必须保留 requires_approval / requires_allowlist / requires_gray_window。",
    route: "/admin/p1/group-ops-workspace"
  },
  {
    key: "ops_plan_broadcast",
    title: "编排预览",
    status: "downstream-pending",
    evidenceStatus: "EVIDENCE_COLLECTED",
    derivedStatus: "broadcast_job_pending",
    summary: "编排 shell 只展示 preview；下游 external effect 未执行，不能渲染为 completed。",
    guardrail: "requires_push_center / no_direct_send / no_external_call / no_production_write。",
    route: "/admin/cloud-orchestrator/plans"
  },
  {
    key: "wecom_auth",
    title: "执行配置",
    status: "external-config-blocked",
    evidenceStatus: "BLOCKED_CONFIG_NOT_APPROVED",
    derivedStatus: "external_config_exception",
    summary: "企微配置仍是 external-config-blocked，不进入可执行队列。",
    guardrail: "需要外部配置批准后才能进入真实授权或 callback 取证。",
    route: "/admin/channels"
  }
];

export const P1_GROUP_OPS_WORKSPACE_FIXTURE: WorkspaceFixture = {
  payload: {
    finalVerdict: "P1_READY_WITH_EXCEPTIONS",
    canClaimPass90Plus: false,
    scenarios: GROUP_OPS_WORKSPACE_SCENARIOS
  },
  leftRailItems: [
    {
      id: "plan-p1-group-ops-preview",
      label: "P1 群运营测试计划",
      kind: "plan",
      entityType: "plan",
      detailId: "plan-p1-group-ops-preview",
      status: "governance-missing",
      summary: "计划可进入草稿编排预览，但不能发送或审批。"
    },
    {
      id: "audience-redacted-segment",
      label: "脱敏人群包",
      kind: "group",
      entityType: "group",
      detailId: "group-redacted-summary",
      status: "evidence-incomplete",
      summary: "仅用于布局占位，不包含真实 receiver 明文。"
    },
    {
      id: "task-push-center-preview",
      label: "Push Center preview",
      kind: "node",
      entityType: "node",
      detailId: "node-preview-task",
      status: "downstream-pending",
      summary: "任务流只读预览，必须经 Push Center gate。"
    },
    {
      id: "execution-preview-empty",
      label: "Execution preview",
      kind: "execution",
      entityType: "execution",
      detailId: "execution-preview-empty",
      status: "pending",
      summary: "只读执行记录占位，不代表 workspace 触发过执行。"
    },
    {
      id: "push-center-preview",
      label: "Push Center projection",
      kind: "push_center",
      entityType: "push_center",
      detailId: "push-center-preview",
      status: "evidence-incomplete",
      summary: "未绑定真实 projection，不能伪造成 sent。"
    },
    {
      id: "evidence-p1-governance",
      label: "Evidence / guardrails",
      kind: "evidence",
      entityType: "evidence",
      detailId: "evidence-p1-governance",
      status: "governance-missing",
      summary: "发送 evidence 不等于 governance complete；approval / allowlist / gray-window 仍缺失。"
    }
  ],
  detailItems: [
    {
      id: "plan-p1-group-ops-preview",
      entityType: "plan",
      title: "P1 群运营测试计划",
      status: "governance-missing",
      evidenceStatus: "fixture_fallback",
      derivedStatus: "draft_only_preview_only",
      summary: "计划只用于 workspace 结构验证；不会审批、发送或写生产。",
      guardrail: "requires_approval / requires_allowlist / requires_gray_window。",
      fields: [
        { label: "plan_id", value: "plan-p1-group-ops-preview" },
        { label: "status", value: "governance-missing" },
        { label: "mode", value: "draft-only / preview-only" }
      ]
    },
    {
      id: "group-redacted-summary",
      entityType: "group",
      title: "脱敏人群包",
      status: "evidence-incomplete",
      evidenceStatus: "fixture_fallback",
      derivedStatus: "receiver_summary_redacted",
      summary: "仅展示聚合人群摘要，不展示 receiver 或成员明文。",
      guardrail: "requires_allowlist / no_direct_send。",
      fields: [
        { label: "group_summary", value: "redacted aggregate only" },
        { label: "sensitive_data", value: "removed" }
      ]
    },
    {
      id: "node-preview-task",
      entityType: "node",
      title: "Push Center preview node",
      status: "downstream-pending",
      evidenceStatus: "fixture_fallback",
      derivedStatus: "push_center_gate_required",
      summary: "任务节点仅支持只读预览；不保存、不执行。",
      guardrail: "requires_push_center / no_external_call / no_production_write。",
      fields: [
        { label: "node_type", value: "preview" },
        { label: "execution", value: "not executed" }
      ]
    },
    {
      id: "execution-preview-empty",
      entityType: "execution",
      title: "Execution preview",
      status: "pending",
      evidenceStatus: "fixture_fallback",
      derivedStatus: "execution_not_selected",
      summary: "暂无真实执行记录；保持 pending，不渲染为 sent。",
      guardrail: "preview_only / no_direct_send。",
      fields: [
        { label: "execution_id", value: "not_provided" },
        { label: "real_external_call", value: "false" }
      ]
    },
    {
      id: "push-center-preview",
      entityType: "push_center",
      title: "Push Center projection",
      status: "evidence-incomplete",
      evidenceStatus: "fixture_fallback",
      derivedStatus: "projection_not_linked",
      summary: "未绑定真实 projection；不能伪造成已发送。",
      guardrail: "requires_push_center / no_direct_send。",
      fields: [
        { label: "projection_id", value: "not_found" },
        { label: "can_claim_pass_90_plus", value: "false" }
      ]
    },
    {
      id: "evidence-p1-governance",
      entityType: "evidence",
      title: "Evidence / guardrail summary",
      status: "governance-missing",
      evidenceStatus: "fixture_fallback",
      derivedStatus: "approval_allowlist_window_missing",
      summary: "fixture 只说明治理证据缺口；不能把 sent 渲染成 governance complete。",
      guardrail: "requires_approval / requires_allowlist / requires_gray_window。",
      fields: [
        { label: "approval_evidence", value: "missing" },
        { label: "allowlist_evidence", value: "missing" },
        { label: "gray_window_evidence", value: "missing" },
        { label: "can_claim_pass_90_plus", value: "false" }
      ]
    }
  ],
  defaultSelection: {
    selectedPlanId: "plan-p1-group-ops-preview",
    selectedGroupId: "group-redacted-summary",
    selectedNodeId: "node-preview-task",
    selectedExecutionId: "execution-preview-empty",
    selectedPushCenterJobId: "push-center-preview",
    selectedEntityType: "plan"
  },
  workspaceMode: "draft_only_preview_only",
  dataSourceLabel: "fixture_fallback",
  dataBindingStatus: "fixture_fallback",
  realExternalCallExecuted: false,
  productionWriteExecuted: false
};

export function createUnavailableWorkspaceFixture(dataSourceLabel = "read_only_api_unavailable"): WorkspaceFixture {
  return {
    ...P1_GROUP_OPS_WORKSPACE_FIXTURE,
    dataSourceLabel,
    dataBindingStatus: "real_data_unavailable",
    leftRailItems: [
      {
        id: "plan-empty",
        label: "No Group Ops plan found",
        kind: "plan",
        entityType: "plan",
        detailId: "plan-p1-group-ops-preview",
        status: "evidence-incomplete",
        summary: "只读 API 不可用或没有可绑定计划；不能伪造成 sent。"
      },
      {
        id: "evidence-empty",
        label: "Evidence unavailable",
        kind: "evidence",
        entityType: "evidence",
        detailId: "evidence-p1-governance",
        status: "evidence-incomplete",
        summary: "只读数据不可用；治理 evidence 保持 incomplete。"
      }
    ],
    payload: {
      finalVerdict: "P1_READY_WITH_EXCEPTIONS",
      canClaimPass90Plus: false,
      scenarios: [
        {
          key: "group_ops",
          title: "Group Ops real-data binding",
          status: "evidence-incomplete",
          evidenceStatus: "REAL_DATA_UNAVAILABLE",
          derivedStatus: "read_only_api_unavailable",
          summary: "只读数据不可用，保留 preview-only fallback。",
          guardrail: "API 失败不能渲染为 sent/completed，也不能 claim PASS_90_PLUS。",
          route: "/admin/automation-conversion/group-ops/ui"
        }
      ]
    }
  };
}
