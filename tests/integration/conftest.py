"""Integration test fixtures — 跑核心业务路径在真实数据库（PG）上。

行为：
- 必须设置 ``DATABASE_URL=postgresql://...``；无 PG 时整组 integration test skip。
- 复用顶层 ``tests.conftest`` 的 schema 初始化、truncate 隔离和 Flask app helper。

CI 上跑 PG 集成测试只需 ``DATABASE_URL=postgresql://test:test@localhost:5432/test pytest tests/integration/``。
"""
from __future__ import annotations

from typing import Any, Iterator

import pytest


@pytest.fixture
def app(tmp_path: Any) -> Iterator[Any]:
    """Flask app + 真实 PG，复用普通测试的统一建表/清表逻辑。"""
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path) as app:
        yield app


@pytest.fixture
def db_backend() -> str:
    """历史 fixture：SQLite 已移除，integration tests 固定是 PG。"""
    return "postgres"
