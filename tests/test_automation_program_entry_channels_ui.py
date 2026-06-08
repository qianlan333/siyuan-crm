from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP_TEMPLATE = ROOT / "aicrm_next" / "automation_engine" / "templates" / "admin_console" / "automation_program_setup_next.html"
ENTRY_TEMPLATE = ROOT / "aicrm_next" / "automation_engine" / "templates" / "admin_console" / "automation_conversion_entry_channels.html"
CHANNEL_JS = ROOT / "aicrm_next" / "automation_engine" / "static" / "admin_console" / "channel_admission_pages.js"


def test_setup_entry_step_reuses_entry_channel_binding_js():
    setup_html = SETUP_TEMPLATE.read_text(encoding="utf-8")
    entry_html = ENTRY_TEMPLATE.read_text(encoding="utf-8")
    channel_js = CHANNEL_JS.read_text(encoding="utf-8")

    assert channel_js.count("function setupBindModal()") == 1
    assert channel_js.count("function setupEntryActions()") == 1
    assert "data-channel-admission-page=\"entry-channels\"" in setup_html
    assert "data-open-bind-modal" in setup_html
    assert "data-confirm-bind" in setup_html
    assert "data-unbind-channel" in setup_html
    assert "channel_admission_pages.js" in setup_html
    assert "channel_admission_pages.js" in entry_html
    assert "bind_program_channels" not in setup_html
