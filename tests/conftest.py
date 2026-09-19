import copy
import importlib
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend-tickets"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

BASE_CFG = {
    "chapter_id": "test-chapter",
    "product_name": "Punarmilan - The Reunion",
    "chapter_name": "Test City Alumni Chapter",
    "event": {
        "name": "Test Reunion & Mixer",
        "date_label": "Saturday, November 7, 2026",
        "date_short": "Nov 7",
        "date_badge": {"month": "NOV", "day": "7", "year": "2026"},
        "time_label": "1:00 PM – 5:00 PM",
        "city_label": "Test City",
        "venue_name": "Hall <One>",
        "venue_address": "1 Main St, Test City",
        "venue_maps_url": "https://maps.example.com/abc?x=1&y=2",
    },
    "contact": {
        "name": "Pat Tester",
        "title": "Chapter Lead",
        "phone": "+1 (555) 000-1111",
        "phone_tel": "+15550001111",
        "email": "pat@example.org",
    },
    "whatsapp_group_url": "https://chat.whatsapp.com/TESTGROUP",
    "content": {"invite_email": "Hello **friends** - we're back!\n\nSee *you* at [our site](https://example.org/?a=1&b=2)."},
}


@pytest.fixture
def make_email_utils(tmp_path, monkeypatch):
    """Load email_utils against a custom chapter config; capture what would be sent."""

    def build(overrides=None):
        cfg = copy.deepcopy(BASE_CFG)
        for k, v in (overrides or {}).items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
        path = tmp_path / "chapter_config.json"
        path.write_text(json.dumps(cfg))
        monkeypatch.setenv("CHAPTER_CONFIG_PATH", str(path))
        import chapter_config

        importlib.reload(chapter_config)
        chapter_config.reset_cache_for_tests()
        import email_utils

        importlib.reload(email_utils)
        sent = []
        monkeypatch.setattr(
            email_utils,
            "send_email",
            lambda to, subject, body, images=None: sent.append({"to": to, "subject": subject, "html": body, "images": images}) or (True, None),
        )
        return email_utils, sent

    return build
