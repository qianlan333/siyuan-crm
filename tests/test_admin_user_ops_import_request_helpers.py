from __future__ import annotations

from io import BytesIO

import pytest
from flask import Flask

from wecom_ability_service.http.admin_user_ops import _run_user_ops_text_or_file_import


class _DummyDTO:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _DummyCommand:
    def __call__(self, dto: _DummyDTO):
        return dto.kwargs


def test_user_ops_import_helper_reads_json_pasted_text():
    app = Flask(__name__)

    with app.test_request_context(method="POST", json={"pasted_text": "  13800138000  "}):
        payload = _run_user_ops_text_or_file_import(_DummyCommand, _DummyDTO)

    assert payload == {"pasted_text": "13800138000"}


def test_user_ops_import_helper_reads_plain_text_body():
    app = Flask(__name__)

    with app.test_request_context(method="POST", data="  13800138001  ", content_type="text/plain"):
        payload = _run_user_ops_text_or_file_import(_DummyCommand, _DummyDTO)

    assert payload == {"pasted_text": "13800138001"}


def test_user_ops_import_helper_prefers_uploaded_file():
    app = Flask(__name__)

    with app.test_request_context(
        method="POST",
        data={"file": (BytesIO(b"mobile,class_term\n13800138002,5"), "class-term.csv")},
        content_type="multipart/form-data",
    ):
        payload = _run_user_ops_text_or_file_import(_DummyCommand, _DummyDTO)

    assert payload == {
        "file_name": "class-term.csv",
        "file_bytes": b"mobile,class_term\n13800138002,5",
    }


def test_user_ops_import_helper_rejects_empty_payload():
    app = Flask(__name__)

    with app.test_request_context(method="POST", json={"pasted_text": "   "}):
        with pytest.raises(ValueError, match="file or pasted_text is required"):
            _run_user_ops_text_or_file_import(_DummyCommand, _DummyDTO)
