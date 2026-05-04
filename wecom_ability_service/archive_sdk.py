from __future__ import annotations

import base64
import ctypes
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from flask import current_app

from .infra.settings import get_setting


class WeComArchiveError(RuntimeError):
    pass


SDK_PTR = ctypes.c_void_p
SLICE_PTR = ctypes.c_void_p


def configure_sdk(lib_path: str):
    if not Path(lib_path).exists():
        raise FileNotFoundError(f"SDK library not found: {lib_path}")

    lib = ctypes.CDLL(lib_path)
    lib.NewSdk.argtypes = []
    lib.NewSdk.restype = SDK_PTR
    lib.Init.argtypes = [SDK_PTR, ctypes.c_char_p, ctypes.c_char_p]
    lib.Init.restype = ctypes.c_int
    lib.DestroySdk.argtypes = [SDK_PTR]
    lib.DestroySdk.restype = None
    lib.NewSlice.argtypes = []
    lib.NewSlice.restype = SLICE_PTR
    lib.FreeSlice.argtypes = [SLICE_PTR]
    lib.FreeSlice.restype = None
    lib.GetChatData.argtypes = [
        SDK_PTR,
        ctypes.c_ulonglong,
        ctypes.c_uint,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_int,
        SLICE_PTR,
    ]
    lib.GetChatData.restype = ctypes.c_int
    lib.GetContentFromSlice.argtypes = [SLICE_PTR]
    lib.GetContentFromSlice.restype = ctypes.c_char_p
    lib.DecryptData.argtypes = [ctypes.c_char_p, ctypes.c_char_p, SLICE_PTR]
    lib.DecryptData.restype = ctypes.c_int
    return lib


def get_slice_text(lib, slice_ptr: SLICE_PTR) -> str:
    raw = lib.GetContentFromSlice(slice_ptr)
    return raw.decode("utf-8") if raw else ""


def load_private_key(private_key_path: str):
    key_bytes = Path(private_key_path).read_bytes()
    return serialization.load_pem_private_key(key_bytes, password=None)


def decrypt_random_key(private_key_path: str, encrypted_random_key: str, publickey_ver: int) -> str:
    if int(publickey_ver) != 1:
        raise WeComArchiveError(f"unsupported publickey_ver: {publickey_ver}")

    private_key = load_private_key(private_key_path)
    cipher_bytes = base64.b64decode(encrypted_random_key)
    paddings = [
        padding.PKCS1v15(),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA1()), algorithm=hashes.SHA1(), label=None),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    ]

    last_error = None
    for rsa_padding in paddings:
        try:
            plain = private_key.decrypt(cipher_bytes, rsa_padding)
            return plain.decode("utf-8")
        except Exception as exc:
            last_error = exc

    raise WeComArchiveError(f"failed to decrypt random key: {last_error}")


def fetch_chatdata_page(lib, sdk_ptr: SDK_PTR, seq: int, limit: int, timeout: int) -> dict[str, Any]:
    chat_slice = None
    try:
        chat_slice = lib.NewSlice()
        if not chat_slice:
            raise WeComArchiveError("NewSlice for GetChatData returned null")

        get_ret = lib.GetChatData(
            sdk_ptr,
            seq,
            limit,
            None,
            None,
            timeout,
            chat_slice,
        )
        if get_ret != 0:
            raise WeComArchiveError(f"GetChatData failed with code {get_ret}")
        return json.loads(get_slice_text(lib, chat_slice) or "{}")
    finally:
        if chat_slice:
            lib.FreeSlice(chat_slice)


def decrypt_chat_payload(lib, private_key_path: str, encrypted_record: dict[str, Any]) -> dict[str, Any]:
    random_key = decrypt_random_key(
        private_key_path,
        encrypted_record["encrypt_random_key"],
        int(encrypted_record.get("publickey_ver", 0)),
    )

    decrypt_slice = None
    try:
        decrypt_slice = lib.NewSlice()
        if not decrypt_slice:
            raise WeComArchiveError("NewSlice for DecryptData returned null")

        decrypt_ret = lib.DecryptData(
            random_key.encode("utf-8"),
            encrypted_record["encrypt_chat_msg"].encode("utf-8"),
            decrypt_slice,
        )
        if decrypt_ret != 0:
            raise WeComArchiveError(f"DecryptData failed with code {decrypt_ret}")
        return json.loads(get_slice_text(lib, decrypt_slice) or "{}")
    finally:
        if decrypt_slice:
            lib.FreeSlice(decrypt_slice)


def normalize_timestamp(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str) and "-" in value and ":" in value:
        return value
    ts = int(value)
    if ts > 10_000_000_000:
        ts = ts // 1000
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def is_external_userid(value: str | None) -> bool:
    return bool(value) and value.startswith(("wm", "wo"))


def first_non_empty(values: list[str | None]) -> str:
    for value in values:
        if value:
            return value
    return ""


def extract_text_record(
    seq: int,
    encrypted_record: dict[str, Any],
    decrypted_payload: dict[str, Any],
    fallback_owner_userid: str = "",
) -> dict[str, Any] | None:
    if decrypted_payload.get("msgtype") != "text":
        return None

    sender = decrypted_payload.get("from", "")
    tolist = decrypted_payload.get("tolist") or []
    if isinstance(tolist, str):
        tolist = [tolist]
    roomid = decrypted_payload.get("roomid", "") or ""
    chat_type = "group" if roomid else ("private" if len(tolist) == 1 else "group")

    external_candidates = [item for item in [sender, *tolist] if is_external_userid(item)]
    internal_candidates = [item for item in [sender, *tolist] if item and not is_external_userid(item)]
    external_userid = first_non_empty(external_candidates) or ""
    owner_userid = sender if sender and not is_external_userid(sender) else first_non_empty(internal_candidates)
    owner_userid = owner_userid or fallback_owner_userid
    content = ((decrypted_payload.get("text") or {}).get("content") or "").strip()

    if not owner_userid or not content:
        return None

    combined_payload = {
        "seq": seq,
        "encrypted_record": encrypted_record,
        "decrypted_message": decrypted_payload,
    }

    return {
        "seq": seq,
        "msgid": decrypted_payload.get("msgid") or encrypted_record.get("msgid") or f"seq-{seq}",
        "chat_type": chat_type,
        "external_userid": external_userid,
        "owner_userid": owner_userid,
        "sender": sender,
        "receiver": ",".join(tolist),
        "msgtype": "text",
        "content": content,
        "send_time": normalize_timestamp(decrypted_payload.get("msgtime") or decrypted_payload.get("send_time")),
        "raw_payload": json.dumps(combined_payload, ensure_ascii=False),
    }


def get_archive_config() -> dict[str, Any]:
    return {
        "corp_id": get_setting("WECOM_CORP_ID") or current_app.config["WECOM_CORP_ID"],
        "archive_secret": get_setting("WECOM_ARCHIVE_SECRET") or current_app.config["WECOM_ARCHIVE_SECRET"],
        "private_key_path": get_setting("WECOM_PRIVATE_KEY_PATH") or current_app.config["WECOM_PRIVATE_KEY_PATH"],
        "sdk_lib_path": get_setting("WECOM_SDK_LIB_PATH") or current_app.config["WECOM_SDK_LIB_PATH"],
        "default_owner_userid": get_setting("WECOM_DEFAULT_OWNER_USERID") or current_app.config["WECOM_DEFAULT_OWNER_USERID"],
        "timeout": int(get_setting("WECOM_ARCHIVE_TIMEOUT") or current_app.config["WECOM_ARCHIVE_TIMEOUT"]),
    }
