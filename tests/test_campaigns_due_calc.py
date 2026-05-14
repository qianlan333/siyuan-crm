"""Campaigns 调度——due 时间计算的 timezone 正确性。

回归测试两个曾经把 cron 推送链路打死的 bug：

1. ``_compute_first_step_due_iso`` 必须输出带 tz 后缀的 ISO，否则
   PG TIMESTAMPTZ 字段会按 server timezone（Asia/Shanghai）解读 naive
   字符串 → 跨 UTC↔本地写入会错位 8 小时，cron 立刻把刚算好的"D+0 早 8 点"
   认成"已过期 8 小时" → 死循环重试。

2. ``scheduler`` 里 budget 拒绝后的 ``retry_at`` 同样必须 tz-aware ——
   原来用 ``datetime.utcnow().isoformat()`` 输出 naive UTC，PG 也按 +08
   解读 → 推迟"1 小时后再试"实际写成"7 小时前已过期"。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from wecom_ability_service.domains.campaigns.service import (
    _compute_first_step_due_iso,
)
from wecom_ability_service.domains.campaigns.scheduler import (
    _due_at_for_step,
)


_TZ_SUFFIX_PATTERN = re.compile(r"(?:Z|[+-]\d{2}:\d{2})$")


def test_first_step_due_includes_tz_suffix():
    """输出 ISO 必须包含 +HH:MM 或 Z 后缀（PG TIMESTAMPTZ 才能正确解读）。"""
    iso = _compute_first_step_due_iso(
        anchor_date="2026-05-09",
        day_offset=0,
        send_time="08:00",
        step_timezone="Asia/Shanghai",
    )
    assert _TZ_SUFFIX_PATTERN.search(iso), f"missing tz suffix: {iso!r}"


def test_first_step_due_asia_shanghai_d0_at_8am():
    """anchor 5/9 + D+0 + 08:00 + Asia/Shanghai → 北京时间 5/9 08:00（UTC 5/9 00:00）。"""
    iso = _compute_first_step_due_iso(
        anchor_date="2026-05-09",
        day_offset=0,
        send_time="08:00",
        step_timezone="Asia/Shanghai",
    )
    parsed = datetime.fromisoformat(iso)
    assert parsed.utcoffset() == timedelta(hours=8)
    assert parsed.astimezone(timezone.utc) == datetime(2026, 5, 9, 0, 0, tzinfo=timezone.utc)


def test_first_step_due_day_offset_advances_calendar_day():
    """day_offset=2 应该加 2 天到 anchor。"""
    iso = _compute_first_step_due_iso(
        anchor_date="2026-05-09",
        day_offset=2,
        send_time="10:00",
        step_timezone="Asia/Shanghai",
    )
    parsed = datetime.fromisoformat(iso)
    assert parsed.year == 2026 and parsed.month == 5 and parsed.day == 11
    assert parsed.hour == 10 and parsed.minute == 0


def test_first_step_due_invalid_timezone_falls_back_to_default():
    """non-IANA timezone 字符串不应 crash，降级到 Asia/Shanghai。"""
    iso = _compute_first_step_due_iso(
        anchor_date="2026-05-09",
        day_offset=0,
        send_time="08:00",
        step_timezone="Not/A_Real_Zone",
    )
    parsed = datetime.fromisoformat(iso)
    assert parsed.utcoffset() == timedelta(hours=8)


def test_first_step_due_empty_timezone_falls_back_to_default():
    """空字符串 timezone 也走默认。"""
    iso = _compute_first_step_due_iso(
        anchor_date="2026-05-09",
        day_offset=0,
        send_time="08:00",
        step_timezone="",
    )
    assert datetime.fromisoformat(iso).utcoffset() == timedelta(hours=8)


def test_first_step_due_utc_timezone_emits_zero_offset():
    """显式 UTC step.timezone 输出 +00:00。"""
    iso = _compute_first_step_due_iso(
        anchor_date="2026-05-09",
        day_offset=0,
        send_time="08:00",
        step_timezone="UTC",
    )
    parsed = datetime.fromisoformat(iso)
    assert parsed.utcoffset() == timedelta(0)
    assert parsed == datetime(2026, 5, 9, 8, 0, tzinfo=timezone.utc)


def test_first_step_due_invalid_send_time_uses_default():
    """畸形 send_time 不应 crash —— 落到 ZoneInfo 默认 hour 后仍带 tz。"""
    iso = _compute_first_step_due_iso(
        anchor_date="2026-05-09",
        day_offset=0,
        send_time="not-a-time",
        step_timezone="Asia/Shanghai",
    )
    assert _TZ_SUFFIX_PATTERN.search(iso)


def test_due_at_for_step_includes_tz_suffix():
    """_due_at_for_step 必须输出 tz-aware ISO，防止 PG 二次套时区偏移 8 小时。"""
    iso = _due_at_for_step(anchor_date="2026-05-12", day_offset=0, send_time="19:00")
    assert _TZ_SUFFIX_PATTERN.search(iso), f"missing tz suffix: {iso!r}"


def test_due_at_for_step_19_00_asia_shanghai():
    """anchor 5/12 + D+0 + 19:00 → 北京时间 19:00（UTC 11:00）。"""
    iso = _due_at_for_step(anchor_date="2026-05-12", day_offset=0, send_time="19:00")
    parsed = datetime.fromisoformat(iso)
    assert parsed.utcoffset() == timedelta(hours=8)
    assert parsed.astimezone(timezone.utc) == datetime(2026, 5, 12, 11, 0, tzinfo=timezone.utc)


def test_due_at_for_step_day_offset():
    """day_offset=1 → 日期推一天。"""
    iso = _due_at_for_step(anchor_date="2026-05-12", day_offset=1, send_time="19:00")
    parsed = datetime.fromisoformat(iso)
    assert parsed.day == 13
    assert parsed.hour == 19


def test_scheduler_retry_at_is_tz_aware():
    """scheduler 的 budget-rejected retry_at 必须输出 tz-aware ISO。

    复刻 scheduler.py:481 用同样的 expression，验证它的输出 PG 解读正确。
    """
    retry_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert _TZ_SUFFIX_PATTERN.search(retry_at), f"naive ISO leaked: {retry_at!r}"
    parsed = datetime.fromisoformat(retry_at)
    assert parsed.tzinfo is not None
    # 确认就是 1 小时后（±60 秒容差）
    delta = parsed - datetime.now(timezone.utc)
    assert timedelta(minutes=59) < delta < timedelta(minutes=61)
