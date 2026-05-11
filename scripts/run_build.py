from __future__ import annotations

import compileall
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _compile_targets() -> bool:
    targets = [
        ROOT / "wecom_ability_service",
        ROOT / "tests",
        ROOT / "scripts",
    ]
    return all(compileall.compile_dir(str(path), quiet=1, force=False) for path in targets if path.exists())


def _flask_smoke_build() -> None:
    from wecom_ability_service import create_app
    from wecom_ability_service.db import init_db

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        private_key_path = tmp_path / "wecom_private_key.pem"
        sdk_lib_path = tmp_path / "libWeWorkFinanceSdk_C.so"
        private_key_path.write_text("fake-key", encoding="utf-8")
        sdk_lib_path.write_text("fake-so", encoding="utf-8")
        app = create_app(
            {
                "TESTING": True,
                # DATABASE_URL 从环境变量读取（PG-only，2026-05 砍 SQLite 后不再需要 DATABASE_PATH）
                "RELEASE_SHA": "build-smoke",
                "WECOM_CORP_ID": "ww-build",
                "WECOM_CONTACT_SECRET": "contact-secret-build",
                "WECOM_SECRET": "secret-build",
                "WECOM_AGENT_ID": "1000002",
                "WECOM_ARCHIVE_SECRET": "archive-secret-build",
                "WECOM_API_BASE": "http://fake-wecom.local",
                "WECOM_PRIVATE_KEY_PATH": str(private_key_path),
                "WECOM_SDK_LIB_PATH": str(sdk_lib_path),
                "WECOM_CALLBACK_TOKEN": "callback-token",
                "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
                "MCP_BEARER_TOKEN": "mcp-token",
                "AUTOMATION_INTERNAL_API_TOKEN": "internal-token",
            }
        )
        with app.app_context():
            init_db()
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["admin_session_user_id"] = 0
            sess["admin_session_wecom_userid"] = ""
            sess["admin_session_role_list"] = ["super_admin"]
            sess["admin_session_login_type"] = "break_glass"
            sess["admin_session_display_name"] = "build-smoke"
            sess["admin_session_break_glass_username"] = "build-smoke"
        response = client.get("/admin/customers")
        if response.status_code not in (200, 302):
            raise SystemExit(f"build smoke customers route failed: status={response.status_code}")


def main() -> int:
    if not _compile_targets():
        print("compileall failed")
        return 1
    _flask_smoke_build()
    print("build ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
