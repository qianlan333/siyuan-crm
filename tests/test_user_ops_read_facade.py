from __future__ import annotations


def test_user_ops_domain_read_facades_share_page_service_owner(monkeypatch):
    from wecom_ability_service.domains.user_ops import service as user_ops_service

    calls: list[tuple[str, dict[str, object]]] = []

    def fake_list_user_ops_pool(**kwargs):
        calls.append(("list", kwargs))
        return {"kind": "list"}

    def fake_get_user_ops_overview(**kwargs):
        calls.append(("overview", kwargs))
        return {"kind": "overview"}

    def fake_export_user_ops_pool(**kwargs):
        calls.append(("export", kwargs))
        return {"kind": "export"}

    monkeypatch.setattr(user_ops_service.page_service, "list_user_ops_pool", fake_list_user_ops_pool)
    monkeypatch.setattr(user_ops_service.page_service, "get_user_ops_overview", fake_get_user_ops_overview)
    monkeypatch.setattr(user_ops_service.page_service, "export_user_ops_pool", fake_export_user_ops_pool)

    shared_kwargs = {
        "wecom_status": "added",
        "mobile_binding_status": "bound",
        "activation_bucket": "activated",
        "is_wecom_added": "1",
        "is_mobile_bound": "1",
        "huangxiaocan_activation_state": "activated",
        "class_term_no": "8",
        "keyword": "客户",
        "mobile": "13800138000",
        "owner_userid": "sales_01",
        "query": "客户",
    }

    assert user_ops_service.list_user_ops_pool(**shared_kwargs) == {"kind": "list"}
    assert user_ops_service.get_user_ops_overview(**shared_kwargs) == {"kind": "overview"}
    assert user_ops_service.export_user_ops_pool(**shared_kwargs) == {"kind": "export"}
    assert calls == [
        ("list", shared_kwargs),
        ("overview", shared_kwargs),
        ("export", shared_kwargs),
    ]
