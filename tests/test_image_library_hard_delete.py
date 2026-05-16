"""image_library 硬删除（PR-E）的测试。

覆盖：
- find_image_references 找 miniprogram_library / campaign_steps 引用
- delete_image 默认行为：无引用直接 DELETE，记录从表里消失
- delete_image 默认行为：有引用抛 ValueError 含引用计数
- delete_image(force=True)：cascade 清理 thumb_image_id 置 NULL
- delete_image(force=True)：cascade 清理 campaign_steps.image_library_ids 数组里移除
- delete_image：不存在的 id 抛 ValueError "not found"
- HTTP endpoint：?force=true 透传；引用错误返回 409 + references；not found 404
"""
from __future__ import annotations

import base64
import json

import pytest

from wecom_ability_service.db import get_db
from wecom_ability_service.domains import image_library


_TINY_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAEAAAcAAekVCC0AAAAASUVORK5CYII="
)


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(
        tmp_path,
        MCP_BEARER_TOKEN="mcp-token",
        AUTOMATION_INTERNAL_API_TOKEN="internal-token",
    ) as app:
        yield app


def _create_image(name: str = "test") -> dict:
    return image_library.create_image_from_upload(
        file_bytes=_TINY_PNG_BYTES, file_name=f"{name}.png", mime_type="image/png", name=name,
    )


# ---------- 无引用：直接硬删 ---------- #

def test_delete_image_with_no_refs_removes_row(app):
    with app.app_context():
        img = _create_image("solo")
        result = image_library.delete_image(img["id"])
        assert result["ok"] is True
        assert result["deleted_id"] == img["id"]
        assert result["references_cleared"] == {
            "miniprograms_cleared": 0,
            "campaign_steps_cleared": 0,
        }
        # 表里真的没了
        cur = get_db().cursor()
        cur.execute("SELECT count(*) AS c FROM image_library WHERE id = ?", (img["id"],))
        row = dict(cur.fetchone())
        assert row["c"] == 0


def test_delete_image_not_found_raises(app):
    with app.app_context():
        with pytest.raises(ValueError, match="not found"):
            image_library.delete_image(999999)


# ---------- find_image_references ---------- #

def test_find_image_references_empty_when_unreferenced(app):
    with app.app_context():
        img = _create_image()
        refs = image_library.find_image_references(img["id"])
        assert refs == {"miniprograms": [], "campaign_steps": []}


def test_find_image_references_picks_up_miniprogram(app):
    with app.app_context():
        img = _create_image("for-mini")
        # 直接 INSERT miniprogram_library 引用此图（绕开 service 层校验，简化测试）
        cur = get_db().cursor()
        cur.execute(
            "INSERT INTO miniprogram_library "
            "(name, appid, pagepath, title, thumb_image_id, thumb_image_url, "
            " thumb_image_base64, thumb_media_id, thumb_media_id_expires_at, enabled) "
            "VALUES (?, ?, ?, ?, ?, '', '', '', NULL, TRUE)",
            ("卡片A", "wx-test", "pages/x", "测试卡片", img["id"]),
        )
        get_db().commit()
        refs = image_library.find_image_references(img["id"])
        assert len(refs["miniprograms"]) == 1
        assert refs["miniprograms"][0]["appid"] == "wx-test"


def test_find_image_references_picks_up_campaign_step(app):
    with app.app_context():
        img = _create_image("for-step")
        cur = get_db().cursor()
        payload = json.dumps({"image_library_ids": [img["id"], 999]})
        cur.execute(
            "INSERT INTO campaign_steps "
            "(campaign_id, campaign_segment_id, step_index, content_payload_json) "
            "VALUES (?, ?, ?, ?)",
            (1, 1, 0, payload),
        )
        get_db().commit()
        refs = image_library.find_image_references(img["id"])
        assert len(refs["campaign_steps"]) == 1


def test_find_image_references_does_not_match_substring(app):
    """id=1 不应匹配到 image_library_ids=[12, 21] 这种数字。"""
    with app.app_context():
        img1 = _create_image("substr-1")
        img12 = _create_image("substr-12")
        img21 = _create_image("substr-21")
        cur = get_db().cursor()
        # 创建 step 引用 12 和 21，但**不**引用 1
        payload = json.dumps({"image_library_ids": [img12["id"], img21["id"]]})
        cur.execute(
            "INSERT INTO campaign_steps "
            "(campaign_id, campaign_segment_id, step_index, content_payload_json) "
            "VALUES (?, ?, ?, ?)",
            (1, 1, 0, payload),
        )
        get_db().commit()
        # 查 img1 的引用：应该是空（即使 12/21 包含 "1" 子串）
        refs = image_library.find_image_references(img1["id"])
        assert refs["campaign_steps"] == []
        # 但 img12 / img21 应该都被命中
        assert len(image_library.find_image_references(img12["id"])["campaign_steps"]) == 1
        assert len(image_library.find_image_references(img21["id"])["campaign_steps"]) == 1


# ---------- 有引用 + force=False：拒删 ---------- #

def test_delete_image_with_miniprogram_ref_rejects(app):
    with app.app_context():
        img = _create_image("ref-mini")
        cur = get_db().cursor()
        cur.execute(
            "INSERT INTO miniprogram_library "
            "(name, appid, pagepath, title, thumb_image_id, thumb_image_url, "
            " thumb_image_base64, thumb_media_id, thumb_media_id_expires_at, enabled) "
            "VALUES (?, ?, ?, ?, ?, '', '', '', NULL, TRUE)",
            ("卡片", "wx-y", "p", "t", img["id"]),
        )
        get_db().commit()
        with pytest.raises(ValueError, match="被引用"):
            image_library.delete_image(img["id"])
        # 没删成功，表里还在
        cur.execute("SELECT count(*) AS c FROM image_library WHERE id = ?", (img["id"],))
        assert dict(cur.fetchone())["c"] == 1


def test_delete_image_with_campaign_step_ref_rejects(app):
    with app.app_context():
        img = _create_image("ref-step")
        cur = get_db().cursor()
        cur.execute(
            "INSERT INTO campaign_steps "
            "(campaign_id, campaign_segment_id, step_index, content_payload_json) "
            "VALUES (?, ?, ?, ?)",
            (1, 1, 0, json.dumps({"image_library_ids": [img["id"]]})),
        )
        get_db().commit()
        with pytest.raises(ValueError, match="被引用"):
            image_library.delete_image(img["id"])


# ---------- 有引用 + force=True：cascade 清理后硬删 ---------- #

def test_delete_image_force_clears_miniprogram_thumb(app):
    with app.app_context():
        img = _create_image("force-mini")
        cur = get_db().cursor()
        cur.execute(
            "INSERT INTO miniprogram_library "
            "(name, appid, pagepath, title, thumb_image_id, thumb_image_url, "
            " thumb_image_base64, thumb_media_id, thumb_media_id_expires_at, enabled) "
            "VALUES (?, ?, ?, ?, ?, '', '', '', NULL, TRUE)",
            ("卡片", "wx-z", "p", "t", img["id"]),
        )
        get_db().commit()

        result = image_library.delete_image(img["id"], force=True)
        assert result["ok"] is True
        assert result["references_cleared"]["miniprograms_cleared"] == 1
        # 验证 thumb_image_id 被清成 NULL
        cur.execute("SELECT thumb_image_id FROM miniprogram_library WHERE appid = ?", ("wx-z",))
        row = dict(cur.fetchone())
        assert row["thumb_image_id"] is None
        # 图片本身真的被删了
        cur.execute("SELECT count(*) AS c FROM image_library WHERE id = ?", (img["id"],))
        assert dict(cur.fetchone())["c"] == 0


def test_delete_image_force_removes_from_campaign_step_array(app):
    with app.app_context():
        img = _create_image("force-step")
        keep = _create_image("keep-this")
        cur = get_db().cursor()
        cur.execute(
            "INSERT INTO campaign_steps "
            "(campaign_id, campaign_segment_id, step_index, content_payload_json) "
            "VALUES (?, ?, ?, ?)",
            (1, 1, 0, json.dumps({"image_library_ids": [img["id"], keep["id"]]})),
        )
        get_db().commit()

        result = image_library.delete_image(img["id"], force=True)
        assert result["ok"] is True
        assert result["references_cleared"]["campaign_steps_cleared"] == 1

        # 验证 step 的 image_library_ids 数组里只剩 keep
        cur.execute(
            "SELECT content_payload_json FROM campaign_steps WHERE campaign_id = 1"
        )
        row = dict(cur.fetchone())
        payload = json.loads(row["content_payload_json"]) if isinstance(
            row["content_payload_json"], str
        ) else row["content_payload_json"]
        assert payload["image_library_ids"] == [keep["id"]]


def test_delete_image_force_handles_both_ref_types(app):
    with app.app_context():
        img = _create_image("both-refs")
        cur = get_db().cursor()
        cur.execute(
            "INSERT INTO miniprogram_library "
            "(name, appid, pagepath, title, thumb_image_id, thumb_image_url, "
            " thumb_image_base64, thumb_media_id, thumb_media_id_expires_at, enabled) "
            "VALUES (?, ?, ?, ?, ?, '', '', '', NULL, TRUE)",
            ("卡片", "wx-both", "p", "t", img["id"]),
        )
        cur.execute(
            "INSERT INTO campaign_steps "
            "(campaign_id, campaign_segment_id, step_index, content_payload_json) "
            "VALUES (?, ?, ?, ?)",
            (1, 1, 0, json.dumps({"image_library_ids": [img["id"]]})),
        )
        get_db().commit()

        result = image_library.delete_image(img["id"], force=True)
        assert result["ok"] is True
        assert result["references_cleared"]["miniprograms_cleared"] == 1
        assert result["references_cleared"]["campaign_steps_cleared"] == 1


# ---------- HTTP endpoint 行为 ---------- #

def test_endpoint_delete_no_refs_returns_ok(app):
    with app.app_context():
        img = _create_image("ep-solo")
    client = app.test_client()
    resp = client.delete(f"/api/admin/image-library/{img['id']}")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["ok"] is True
    assert body["deleted_id"] == img["id"]


def test_endpoint_delete_with_refs_returns_409_and_references(app):
    with app.app_context():
        img = _create_image("ep-refs")
        cur = get_db().cursor()
        cur.execute(
            "INSERT INTO campaign_steps "
            "(campaign_id, campaign_segment_id, step_index, content_payload_json) "
            "VALUES (?, ?, ?, ?)",
            (1, 1, 0, json.dumps({"image_library_ids": [img["id"]]})),
        )
        get_db().commit()
    client = app.test_client()
    resp = client.delete(f"/api/admin/image-library/{img['id']}")
    body = resp.get_json()
    assert resp.status_code == 409
    assert body["ok"] is False
    assert "被引用" in body["error"]
    assert "references" in body
    assert len(body["references"]["campaign_steps"]) == 1


def test_endpoint_delete_force_true_cascade_succeeds(app):
    with app.app_context():
        img = _create_image("ep-force")
        cur = get_db().cursor()
        cur.execute(
            "INSERT INTO campaign_steps "
            "(campaign_id, campaign_segment_id, step_index, content_payload_json) "
            "VALUES (?, ?, ?, ?)",
            (1, 1, 0, json.dumps({"image_library_ids": [img["id"]]})),
        )
        get_db().commit()
    client = app.test_client()
    resp = client.delete(f"/api/admin/image-library/{img['id']}?force=true")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["ok"] is True
    assert body["references_cleared"]["campaign_steps_cleared"] == 1


def test_endpoint_delete_not_found_returns_404(app):
    client = app.test_client()
    resp = client.delete("/api/admin/image-library/999999")
    body = resp.get_json()
    assert resp.status_code == 404
    assert body["ok"] is False
    assert "not found" in body["error"]


def test_endpoint_references_endpoint_returns_lists(app):
    with app.app_context():
        img = _create_image("ep-refs-get")
    client = app.test_client()
    resp = client.get(f"/api/admin/image-library/{img['id']}/references")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["ok"] is True
    assert body["references"] == {"miniprograms": [], "campaign_steps": []}
