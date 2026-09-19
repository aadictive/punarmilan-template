import re

# Text that used to be hardcoded for one particular chapter. The emails must only ever contain values
# from the chapter config, so none of it may appear when a different config is loaded.
PERSONAL = re.compile(r"Somaiya|Vidyavihar|Pan-U\.S\.|Samir|Utsav|SOMAIYA-TICKET", re.I)
REG = {"email": "guest@example.org", "name": "Ann <b>Guest</b>", "amount_cents": 6500, "ticket_code": "ABC12345", "selected_payment_method": ""}


def test_confirmation_email_uses_chapter_values(make_email_utils):
    eu, sent = make_email_utils()
    eu.send_registration_confirmed_email(REG)
    mail = sent[0]
    assert mail["subject"] == "You're confirmed! — Test Reunion & Mixer e-ticket"  # subject is plain text, not HTML-escaped
    body = mail["html"]
    assert "Saturday, November 7, 2026" in body and "1:00 PM – 5:00 PM" in body
    assert "Hall &lt;One&gt;" in body and "1 Main St, Test City" in body
    assert 'href="https://maps.example.com/abc?x=1&amp;y=2"' in body
    assert "https://chat.whatsapp.com/TESTGROUP" in body
    assert "Pat Tester" in body and "+1 (555) 000-1111" in body and "pat@example.org" in body
    assert "Chapter Lead, Test City Alumni Chapter" in body
    assert "ABC12345" in body and "ticket_qr" in mail["images"]
    assert not PERSONAL.search(body), PERSONAL.search(body)


def test_registrant_name_cannot_inject_html(make_email_utils):
    eu, sent = make_email_utils()
    eu.send_registration_confirmed_email(REG)
    assert "<b>Guest</b>" not in sent[0]["html"]
    assert "Ann &lt;b&gt;Guest&lt;/b&gt;" in sent[0]["html"]


def test_optional_whatsapp_and_directions_are_omitted_when_blank(make_email_utils):
    eu, sent = make_email_utils({"whatsapp_group_url": "", "event": {"venue_maps_url": ""}})
    eu.send_registration_confirmed_email(REG)
    body = sent[0]["html"]
    assert "WhatsApp" not in body and "Get directions" not in body


def test_invite_email_renders_content_pack_and_buttons(make_email_utils):
    eu, sent = make_email_utils()
    eu.send_invite_email("Bo <i>B</i>", "bo@example.org", "https://site.example/?name=Bo&email=bo@example.org", "https://site.example/decline?x=1&y=2")
    mail = sent[0]
    assert mail["subject"] == "You're invited — Test Reunion & Mixer, Nov 7"
    body = mail["html"]
    assert "Hello <strong>friends</strong>" in body
    assert 'href="https://example.org/?a=1&amp;b=2"' in body
    assert "Yes, I'll be there" in body and "Can't make it this year?" in body
    assert "Hi Bo &lt;i&gt;B&lt;/i&gt;," in body
    assert "&amp;y=2" in body  # decline URL is escaped inside the attribute
    assert not PERSONAL.search(body), PERSONAL.search(body)


def test_payment_emails_have_no_leftover_personal_text(make_email_utils):
    eu, sent = make_email_utils()
    eu.send_payment_reminder_email(dict(REG, selected_payment_method="venmo"), "https://checkout.example/x", 6726, "https://site.example", "@handle", "zelle@example.org")
    eu.send_payment_reminder_email(dict(REG, selected_payment_method="zelle"), "https://checkout.example/x", 6726, "https://site.example", "@handle", "zelle@example.org")
    eu.send_payment_reminder_email(REG, "https://checkout.example/x", 6726, "https://site.example", "", "")
    eu.send_payment_instructions_email(REG, "venmo", "@handle", "")
    eu.send_event_reminder_email(REG)
    eu.send_refund_confirmed_email(REG)
    assert len(sent) == 6
    for mail in sent:
        assert not PERSONAL.search(mail["html"] + mail["subject"]), (mail["subject"], PERSONAL.search(mail["html"]))
    assert "venmo.com/u/handle" in sent[0]["html"]
    assert "Pay $67.26 by card" in sent[2]["html"]


def test_ticket_qr_uses_neutral_prefix(make_email_utils):
    eu, _ = make_email_utils()
    png = eu._ticket_qr_png_bytes("ABC12345")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert eu.TICKET_QR_PREFIX == "PUNARMILAN-TICKET"
