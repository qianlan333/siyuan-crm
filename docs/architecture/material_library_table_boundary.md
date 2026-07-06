# Material Library Table Boundary

PR #15 locks the material-library table boundary without changing upload, picker, or send behavior.

The canonical material tables are:

- `image_library` for reusable image material and cached WeCom image media IDs.
- `miniprogram_library` for reusable mini-program cards, with `thumb_image_id` pointing back to `image_library`.
- `attachment_library` for reusable attachment material.
- `image_library_variants` as a generated image thumbnail/preview read model owned by `image_library`.

The shared cross-module contract remains `SendContentPackage`:

```json
{
  "content_text": "",
  "image_library_ids": [],
  "miniprogram_library_ids": [],
  "attachment_library_ids": []
}
```

Business modules may store these IDs in their own JSON payloads, but they should resolve picker rows through `PostgresSendContentRepository`, which delegates to the media-library repository.
The short-term unified read model is the Next-native `material_assets` projection exposed at `/api/admin/material-assets`.
It returns `asset_type`, `material_asset_id`, `source_table`, and `source_id` over the existing `image_library`, `miniprogram_library`, and `attachment_library` tables.
Material usage lineage is exposed as the read-only `material_asset_usage` projection at `/api/admin/material-assets/{material_asset_id}/usage`, scanning business consumer payloads without moving material rows.
Material validation is exposed as `/api/admin/material-assets/validate`; it checks material existence, enabled state, channel compatibility, metadata completeness, and payload safety without writing to business tables.
This keeps campaign steps, group-ops plan nodes, channel welcome messages, HXC broadcast drafts, and sidebar material views from inventing separate material stores.

The current boundary is intentionally conservative:

- Do not physically merge material tables in PR #15.
- Do not enable real external storage, CDN publishing, or real WeCom media upload.
- Keep `image_library_variants` as a cache/read model, not as a canonical source of material metadata.
- Keep product page slices and other business tables as consumers of `image_library` IDs rather than new media libraries.
- New material consumers should store only `content_text` plus `image_library_ids`, `miniprogram_library_ids`, and `attachment_library_ids`, then use the send-content/material-picker APIs to read normalized picker shapes.
