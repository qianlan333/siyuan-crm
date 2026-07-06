const WORKSPACE_NAME = "P1 Group Ops Workspace";
const DEFAULT_FINAL_VERDICT = "P1_READY_WITH_EXCEPTIONS";
function sensitiveFragments() {
    return [
        "raw_" + "external_userid",
        "receiver_" + "plaintext",
        "raw_" + "receiver",
        "raw_" + "chat",
        "raw_" + "member",
        "raw_" + "message",
        "raw_" + "callback",
        "raw_" + "target",
        "authorization",
        "access_" + "token",
        "corp" + "secret",
        "suite " + "secret",
        "bearer ",
        "token",
        "secret",
        "open" + "id",
        "union" + "id"
    ];
}
function escapedRegExp(value) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
function redactCopyValue(value) {
    let next = String(value ?? "");
    next = next.replace(/\b1[3-9]\d{9}\b/g, "[redacted]");
    next = next.replace(/wrOg[A-Za-z0-9_-]+/g, "[redacted]");
    next = next.replace(/raw[\s_-]+(external[\s_-]*userid|receiver|chat|member|message|callback|target)/gi, "[redacted]");
    for (const fragment of sensitiveFragments()) {
        next = next.replace(new RegExp(escapedRegExp(fragment), "gi"), "[redacted]");
    }
    return next;
}
function safeItemSummary(item) {
    return {
        entityType: item.entityType,
        detailId: redactCopyValue(item.detailId),
        title: redactCopyValue(item.title),
        status: item.status,
        derivedStatus: redactCopyValue(item.derivedStatus),
        visibleInCurrentFilter: item.isVisible
    };
}
function guardrailSummary(bundle) {
    return [
        "This bundle is read-only and cannot execute.",
        "sent evidence is not governance complete.",
        "governance-missing requires approval / allowlist / gray-window.",
        "Push Center pending is not completed.",
        "evidence-incomplete is not success.",
        "Any blocked item means the bundle cannot execute.",
        "P1_READY_WITH_EXCEPTIONS is not PASS_90_PLUS.",
        ...bundle.guardrails.map((guardrail) => redactCopyValue(guardrail))
    ];
}
function buildCopySafeObject(bundle, context = {}) {
    return {
        workspace: context.workspace || WORKSPACE_NAME,
        previewOnly: true,
        productionWrite: false,
        realExternalCall: false,
        canClaimPass90Plus: false,
        finalVerdict: redactCopyValue(context.finalVerdict || DEFAULT_FINAL_VERDICT),
        selectedCount: bundle.selectedCount,
        countsByEntityType: { ...bundle.countsByEntityType },
        blockedCount: bundle.blockedCount,
        actionRequiredCount: bundle.actionRequiredCount,
        governanceMissingCount: bundle.governanceMissingCount,
        pushCenterPendingCount: bundle.pushCenterPendingCount,
        evidenceIncompleteCount: bundle.evidenceIncompleteCount,
        guardrailSummary: guardrailSummary(bundle),
        selectedItems: bundle.items.map((item) => safeItemSummary(item))
    };
}
export function assertCopySafeBundleOutput(output) {
    const lower = output.toLowerCase();
    if (/\b1[3-9]\d{9}\b/.test(output)) {
        throw new Error("copy_safe_output_contains_sensitive_phone_like_value");
    }
    if (/wrOg[A-Za-z0-9_-]+/.test(output)) {
        throw new Error("copy_safe_output_contains_sensitive_member_like_value");
    }
    if (/raw[\s_-]+(external[\s_-]*userid|receiver|chat|member|message|callback|target)/i.test(output)) {
        throw new Error("copy_safe_output_contains_sensitive_raw_value");
    }
    for (const fragment of sensitiveFragments()) {
        if (lower.includes(fragment.toLowerCase())) {
            throw new Error("copy_safe_output_contains_sensitive_fragment");
        }
    }
    return true;
}
export function buildCopySafeBundleJson(bundle, context = {}) {
    const output = JSON.stringify(buildCopySafeObject(bundle, context), null, 2);
    assertCopySafeBundleOutput(output);
    return output;
}
export function buildCopySafeBundleText(bundle, context = {}) {
    const payload = buildCopySafeObject(bundle, context);
    const lines = [
        `${payload.workspace} copy-safe preview bundle`,
        `finalVerdict: ${payload.finalVerdict}`,
        "previewOnly: true",
        "productionWrite: false",
        "realExternalCall: false",
        "canClaimPass90Plus: false",
        `selectedCount: ${payload.selectedCount}`,
        `countsByEntityType: ${JSON.stringify(payload.countsByEntityType)}`,
        `blockedCount: ${payload.blockedCount}`,
        `actionRequiredCount: ${payload.actionRequiredCount}`,
        `governanceMissingCount: ${payload.governanceMissingCount}`,
        `pushCenterPendingCount: ${payload.pushCenterPendingCount}`,
        `evidenceIncompleteCount: ${payload.evidenceIncompleteCount}`,
        "guardrailSummary:",
        ...payload.guardrailSummary.map((guardrail) => `- ${guardrail}`),
        "selectedItems:",
        ...payload.selectedItems.map((item) => (`- ${item.entityType} ${item.detailId}: ${item.title} | ${item.status} | ${item.derivedStatus} | visible=${item.visibleInCurrentFilter}`))
    ];
    const output = lines.join("\n");
    assertCopySafeBundleOutput(output);
    return output;
}
export async function copyBundleSummaryToClipboard(output, clipboard = typeof navigator !== "undefined" ? navigator.clipboard : undefined) {
    try {
        assertCopySafeBundleOutput(output);
        if (!clipboard || typeof clipboard.writeText !== "function") {
            return {
                ok: false,
                status: "copy_failed",
                message: "Clipboard unavailable; no backend fallback was used."
            };
        }
        await clipboard.writeText(output);
        return {
            ok: true,
            status: "copied",
            message: "Copy-safe preview copied. No backend request, file download, or persistent storage was used."
        };
    }
    catch {
        return {
            ok: false,
            status: "copy_failed",
            message: "Copy failed safely; bundle selection was not changed."
        };
    }
}
