from __future__ import annotations

from pathlib import Path

from tools.check_import_graph import scan_import_graph


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_context_import_graph_is_a_dag() -> None:
    report = scan_import_graph(ROOT)

    assert report.cyclic_components == ()
    assert report.cyclic_context_count == 0
    assert report.non_literal_dynamic_imports == ()
