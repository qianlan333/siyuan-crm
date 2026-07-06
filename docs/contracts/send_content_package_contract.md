# SendContentPackage Contract

`SendContentPackage` is the only backend contract for the standard send content component in AI-CRM Next.

This capability is Next-native only. New backend behavior must be implemented under `aicrm_next/send_content` or the existing `aicrm_next/automation_engine` layers. Do not add new `wecom_ability_service/http/*`, `wecom_ability_service/domains/*`, `production_compat`, or legacy facade implementations for this surface.

## Payload

```json
{
  "content_text": "",
  "image_library_ids": [],
  "miniprogram_library_ids": [],
  "attachment_library_ids": []
}
```

Normalization rules:

- `content_text` is trimmed and limited to 4000 characters.
- `image_library_ids` accepts at most 3 positive integer IDs.
- `miniprogram_library_ids` accepts at most 1 positive integer ID.
- `attachment_library_ids` accepts at most 9 positive integer IDs.
- IDs are deduplicated while preserving input order.
- Missing fields normalize to an empty string or empty arrays.
- `text_enabled=false` forces `content_text=""`.
- `require_body=true` requires at least one of text, image IDs, miniprogram IDs, or attachment IDs.
- `require_body=false` allows an empty package for draft saves.

The component outputs only `content_text` plus the three material ID arrays. Outer business pages own their audience, scheduling, sender, and delivery-mode fields.

Frontend usage follows the same boundary. `AICRMSendContentComposer` only edits this package. The retired automation operation-task page no longer owns unified/profile-layered/behavior-layered/agent mode selection, profile template selection, behavior rule selection, or agent selection; new automation targeting belongs to AI Audience packages and agent copywriting flows.

In agent mode the composer must be opened with `textEnabled=false`, so no manual copy is returned and only material IDs are saved.

## HXC Broadcast Usage

HXC / funnel dashboard broadcast also uses `SendContentPackage`. The HXC page supplies audience and sender context, while `AICRMSendContentComposer` supplies only the text and three material ID arrays. HXC broadcast must call the Next-native `/api/admin/hxc-dashboard/broadcast-tasks` API and must not call the old Flask `/api/admin/hxc-dashboard/broadcast` route.

The HXC API normalizes with `require_body=true`, so empty packages are rejected. It does not upload materials to WeCom or resolve `media_id` in this phase.
