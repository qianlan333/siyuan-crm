from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .archive_sdk import (
    WeComArchiveError,
    configure_sdk,
    decrypt_chat_payload,
    extract_text_record,
    fetch_chatdata_page,
    get_archive_config,
)
from .db import get_db
from .services import get_archive_last_seq, insert_archived_messages, materialize_message_batches, set_archive_last_seq

archive_logger = logging.getLogger("archive_sync")


@dataclass
class ArchiveAdapterClient:
    corp_id: str
    archive_secret: str
    private_key_path: str
    sdk_lib_path: str
    default_owner_userid: str
    timeout: int

    @classmethod
    def from_app(cls) -> "ArchiveAdapterClient":
        config = get_archive_config()
        return cls(
            corp_id=config["corp_id"],
            archive_secret=config["archive_secret"],
            private_key_path=config["private_key_path"],
            sdk_lib_path=config["sdk_lib_path"],
            default_owner_userid=config["default_owner_userid"],
            timeout=config["timeout"],
        )

    def health(self) -> dict[str, Any]:
        return {
            "ok": bool(self.corp_id and self.archive_secret),
            "mode": "official-sdk",
            "sdk_lib_path": self.sdk_lib_path,
            "sdk_lib_exists": Path(self.sdk_lib_path).exists(),
            "private_key_path": self.private_key_path,
            "private_key_exists": Path(self.private_key_path).exists(),
        }

    def sync_messages(
        self,
        start_time: str,
        end_time: str,
        owner_userid: str,
        cursor: str = "",
        limit: int = 100,
    ) -> dict[str, Any]:
        if not self.corp_id or not self.archive_secret:
            raise WeComArchiveError("WECOM_CORP_ID or WECOM_ARCHIVE_SECRET is not configured")

        target_owner = owner_userid or self.default_owner_userid
        if not target_owner:
            raise WeComArchiveError("owner_userid is required")

        start_seq = int(cursor) if str(cursor).strip() else get_archive_last_seq()
        archive_logger.info(
            "archive sync started owner_userid=%s start_seq=%s window=%s..%s",
            target_owner,
            start_seq,
            start_time,
            end_time,
        )
        total_fetched = 0
        inserted = 0
        max_seq = start_seq
        batches = []
        external_userids: set[str] = set()
        group_chat_ids: set[str] = set()
        lib = configure_sdk(self.sdk_lib_path)
        sdk_ptr = None
        try:
            sdk_ptr = lib.NewSdk()
            if not sdk_ptr:
                raise WeComArchiveError("NewSdk returned null")

            init_ret = lib.Init(sdk_ptr, self.corp_id.encode("utf-8"), self.archive_secret.encode("utf-8"))
            if init_ret != 0:
                raise WeComArchiveError(f"Init failed with code {init_ret}")

            while True:
                payload = fetch_chatdata_page(lib, sdk_ptr, max_seq, limit, self.timeout)
                encrypted_records = payload.get("chatdata") or []
                if not encrypted_records:
                    break

                total_fetched += len(encrypted_records)
                accepted_rows = []

                for record in encrypted_records:
                    seq = int(record.get("seq", 0))
                    max_seq = max(max_seq, seq)
                    decrypted_payload = decrypt_chat_payload(lib, self.private_key_path, record)
                    normalized = extract_text_record(
                        seq,
                        record,
                        decrypted_payload,
                        fallback_owner_userid=target_owner,
                    )
                    if not normalized:
                        continue
                    if normalized["send_time"] < start_time or normalized["send_time"] > end_time:
                        continue
                    accepted_rows.append(normalized)
                    if normalized.get("external_userid"):
                        external_userids.add(normalized["external_userid"])
                    if normalized.get("chat_type") == "group":
                        try:
                            decrypted = decrypted_payload or {}
                            roomid = decrypted.get("roomid", "")
                        except Exception:
                            roomid = ""
                        if roomid:
                            group_chat_ids.add(roomid)

                db = get_db()
                try:
                    batch_inserted = insert_archived_messages(accepted_rows, commit=False)
                    set_archive_last_seq(max_seq, commit=False)
                    db.commit()
                except Exception:
                    db.rollback()
                    archive_logger.exception(
                        "archive batch transaction failed seq_from=%s seq_to=%s",
                        encrypted_records[0].get("seq"),
                        encrypted_records[-1].get("seq"),
                    )
                    raise
                inserted += batch_inserted
                archive_logger.info(
                    "archive batch seq_from=%s seq_to=%s fetched=%s accepted=%s inserted_total=%s",
                    encrypted_records[0].get("seq"),
                    encrypted_records[-1].get("seq"),
                    len(encrypted_records),
                    len(accepted_rows),
                    inserted,
                )
                batches.append(
                    {
                        "seq_from": encrypted_records[0].get("seq"),
                        "seq_to": encrypted_records[-1].get("seq"),
                        "fetched": len(encrypted_records),
                        "accepted": len(accepted_rows),
                    }
                )

                if len(encrypted_records) < limit:
                    break
        finally:
            if sdk_ptr:
                lib.DestroySdk(sdk_ptr)

        batch_result = materialize_message_batches(window_minutes=3)

        return {
            "messages": [],
            "has_more": False,
            "next_cursor": str(max_seq),
            "fetched_count": total_fetched,
            "inserted_count": inserted,
            "last_seq": max_seq,
            "batches": batches,
            "external_userids": sorted(external_userids),
            "group_chat_ids": sorted(group_chat_ids),
            "message_batching": batch_result,
        }
