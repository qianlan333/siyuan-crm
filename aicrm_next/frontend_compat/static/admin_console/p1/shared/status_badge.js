import { escapeHtml } from "./dom.js";
import { statusMeta } from "./status_model.js";
export function renderStatusBadge(status) {
    const meta = statusMeta(status);
    return `<span class="p1-closure-pill p1-closure-pill--${meta.tone}" data-status-badge="${escapeHtml(status)}">${escapeHtml(meta.label)}</span>`;
}
