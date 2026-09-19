import copy
import os

import prepare
import pytest
import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def cfg():
    with open(os.path.join(ROOT, "tests", "fixtures", "sample.chapter.config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_shipped_sample_config_is_valid_in_normal_mode(cfg):
    errors, _, derived = prepare.validate(cfg, strict=False)
    assert errors == []
    assert derived["date_label"] == "Sunday, October 18, 2026"
    assert derived["date_short"] == "Oct 18" and derived["price_cents"] == 6500


def test_strict_mode_refuses_the_untouched_sample(cfg, monkeypatch):
    monkeypatch.delenv("PUNARMILAN_ALLOW_SAMPLE", raising=False)
    errors, _, _ = prepare.validate(cfg, strict=True)
    joined = " ".join(errors)
    assert "sample-chapter" in joined and "@example.com" in joined


@pytest.mark.parametrize(
    "path,value,fragment",
    [
        (("chapter_id",), "Bad_ID", "chapter_id must be"),
        (("chapter_id",), "ab", "chapter_id must be"),
        (("event", "date"), "18/10/2026", "event.date must look like"),
        (("tickets", "price_usd"), "free", "tickets.price_usd must be a number"),
        (("tickets", "price_usd"), 0.1, "at least 0.50"),
        (("contact", "email"), "not-an-email", "contact.email"),
        (("payments", "venmo_handle"), "has space", "must not contain spaces"),
        (("whatsapp_group_url"), "chat.whatsapp.com/x", "must start with https://"),
        (("registration_form", "expectation_options"), ["only one"], "2 to 8 items"),
    ],
)
def test_bad_values_give_plain_english_errors(cfg, path, value, fragment):
    bad = copy.deepcopy(cfg)
    if isinstance(path, str):
        path = (path,)
    node = bad
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value
    errors, _, _ = prepare.validate(bad, strict=False)
    assert any(fragment in e for e in errors), errors


def test_missing_required_field_is_reported(cfg):
    bad = copy.deepcopy(cfg)
    bad["event"]["venue_name"] = ""
    errors, _, _ = prepare.validate(bad, strict=False)
    assert any("event.venue_name is empty" in e for e in errors)


def test_content_variables_are_resolved_and_typos_caught(cfg, tmp_path, monkeypatch):
    _, _, derived = prepare.validate(cfg, strict=False)
    variables = prepare.build_variables(cfg, derived)
    assert variables["ticket_price"] == "$65"
    (tmp_path / "x.md").write_text("<!-- note -->\nSee you {event_date_short}, {evnt_name}", encoding="utf-8")
    monkeypatch.setattr(prepare, "CONTENT_DIR", str(tmp_path))
    errors = []
    prepare.read_content("x.md", variables, errors)
    assert errors and "{evnt_name}" in errors[0]


def test_placeholder_qr_blocks_a_real_deploy_when_handle_is_set(cfg):
    bad = copy.deepcopy(cfg)
    bad["payments"]["venmo_handle"] = "@someone"
    errors, _ = prepare.check_assets(bad, strict=True)
    assert any("venmo-qr.png is still the placeholder" in e for e in errors)
    ok_errors, _ = prepare.check_assets(cfg, strict=True)  # no handle set -> placeholder is fine
    assert ok_errors == []
