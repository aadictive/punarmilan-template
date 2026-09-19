import importlib
import json

import pytest


def _admin(monkeypatch, admin="admin-pw", view="view-pw"):
    monkeypatch.setenv("ADMIN_PASSWORD", admin)
    monkeypatch.setenv("VIEW_ONLY_PASSWORD", view)
    monkeypatch.setenv("TABLE_NAME", "t")
    import tickets_admin_handler as h

    importlib.reload(h)
    monkeypatch.setattr(h, "_get_all_items", lambda: [{"email": "a@b.co", "status": "paid", "amount_cents": 6500}])
    return h


def _call(h, password):
    return h.handler({"requestContext": {"http": {"method": "GET"}}, "headers": {"x-admin-password": password}}, None)


def test_admin_reports_role_from_server(monkeypatch):
    h = _admin(monkeypatch)
    assert json.loads(_call(h, "admin-pw")["body"])["role"] == "admin"
    assert json.loads(_call(h, "view-pw")["body"])["role"] == "view_only"


def test_admin_rejects_wrong_or_empty_password(monkeypatch):
    h = _admin(monkeypatch)
    assert _call(h, "nope")["statusCode"] == 401
    assert _call(h, "")["statusCode"] == 401
    assert _call(h, "pässwörd")["statusCode"] == 401  # non-ASCII must not crash


def test_view_only_disabled_when_blank(monkeypatch):
    h = _admin(monkeypatch, view="")
    assert _call(h, "")["statusCode"] == 401


HANDLERS = [
    "register_handler", "config_handler", "create_checkout_session_handler", "stripe_webhook_handler",
    "tickets_admin_handler", "select_method_handler", "send_instructions_handler", "send_payment_reminder_handler",
    "admin_checkin_handler", "admin_send_email_handler", "decline_handler", "send_invite_handler",
    "track_view_handler", "mark_paid_handler", "unmark_paid_handler", "checkin_handler",
]


@pytest.mark.parametrize("name", HANDLERS)
def test_every_handler_imports_with_the_generated_config(name):
    module = importlib.import_module(name)
    assert callable(module.handler)
