from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _checker():
    path = ROOT / "scripts/ci/check_unionid_identity_contract.py"
    spec = importlib.util.spec_from_file_location("check_unionid_identity_contract", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unionid_identity_contract_static_gate_is_clean() -> None:
    assert _checker().check() == []
