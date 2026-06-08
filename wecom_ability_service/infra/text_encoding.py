from __future__ import annotations


def repair_utf8_mojibake(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for source_encoding in ("latin1", "cp1252"):
        try:
            repaired = text.encode(source_encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if repaired != text and any("\u4e00" <= char <= "\u9fff" for char in repaired):
            return repaired
    return text
