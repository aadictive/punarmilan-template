#!/usr/bin/env python3
"""
prepare.py - turn chapter.config.yaml + content/ + assets/ into what the build needs.

Run this before `sam build` / `npm run build` (scripts/deploy.sh and the GitHub
Action run it for you). It:

  1. validates chapter.config.yaml and tells you, in plain English, what to fix
  2. writes backend-tickets/chapter_config.json     (read by the Lambda functions)
  3. writes frontend-tickets/src/chapter.generated.json (public settings for the site)
  4. copies the QR-code images and the hero photo from assets/ to where the
     backend and the frontend expect them
  5. writes ready-to-paste WhatsApp / LinkedIn drafts to generated/

Usage:
  python3 scripts/prepare.py              validate + generate everything
  python3 scripts/prepare.py --check      validate only, write nothing
  python3 scripts/prepare.py --strict     also refuse the sample placeholder values
                                          (deploy.sh uses this)
  python3 scripts/prepare.py --get chapter_id     print one value (for shell scripts)
  python3 scripts/prepare.py --sam-params         print Key=Value lines for `sam deploy`
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend-tickets"))
import chapter_config  # noqa: E402  (shared text helpers)

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is missing. Install it with:  pip install pyyaml")

CONFIG_PATH = os.path.join(ROOT, "chapter.config.yaml")
CONTENT_DIR = os.path.join(ROOT, "content")
ASSETS_DIR = os.path.join(ROOT, "assets")

# sha256 of the placeholder images shipped in this repo. If a QR image still
# matches one of these while its payment method is switched on, we refuse to
# build - attendees must never be shown a "REPLACE THIS IMAGE" picture.
PLACEHOLDER_HASHES = {
    "venmo-qr.png": "8443c4dd1860efd26d7d3e40b87ad6e84f48e805052da9d74232c7203725b60f",
    "zelle-qr.png": "4de8ea3d62fb2da82aeb02473a6a4e3ac2527e0ef50e2848af53d6765d85196a",
    "event-photo.jpg": "89e74a72fed469720dceef1d7533f0a9aeee9fcfb698c663010124fc442fb869",
}

SAMPLE_CHAPTER_ID = "sample-chapter"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CHAPTER_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,18}[a-z0-9]$")
NO_SPACE_RE = re.compile(r"^\S+$")
URL_RE = re.compile(r"^https?://\S+$")


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_config():
    if not os.path.exists(CONFIG_PATH):
        sys.exit("chapter.config.yaml not found at the repo root.")
    with open(CONFIG_PATH, encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            sys.exit(
                "chapter.config.yaml is not valid YAML - usually a missing or extra quotation mark.\n"
                f"Details: {e}"
            )
    if not isinstance(data, dict):
        sys.exit("chapter.config.yaml is empty or not a list of settings.")
    return data


def dig(cfg, *keys, default=None):
    cur = cfg
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if cur is not None else default


def validate(cfg, strict):
    """Returns (errors, warnings, derived)."""
    errors, warnings = [], []

    def need(label, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"{label} is empty - please fill it in.")
            return False
        return True

    chapter_id = dig(cfg, "chapter_id", default="")
    if need("chapter_id", chapter_id) and not CHAPTER_ID_RE.match(str(chapter_id)):
        errors.append(
            "chapter_id must be 3-20 characters: lowercase letters, numbers and hyphens, "
            f"starting with a letter (got {chapter_id!r}). Example: somaiya-chicago"
        )

    for label, keys in [
        ("product_name", ("product_name",)),
        ("chapter_name", ("chapter_name",)),
        ("event.name", ("event", "name")),
        ("event.time", ("event", "time")),
        ("event.city", ("event", "city")),
        ("event.venue_name", ("event", "venue_name")),
        ("event.venue_address", ("event", "venue_address")),
        ("contact.name", ("contact", "name")),
        ("contact.title", ("contact", "title")),
    ]:
        need(label, dig(cfg, *keys))

    # date
    date_raw = dig(cfg, "event", "date", default="")
    event_date = None
    if need("event.date", date_raw):
        try:
            event_date = datetime.date.fromisoformat(str(date_raw))
        except ValueError:
            errors.append(f"event.date must look like 2026-10-18 (year-month-day), got {date_raw!r}.")

    # contact
    email = str(dig(cfg, "contact", "email", default="")).strip()
    if need("contact.email", email) and not EMAIL_RE.match(email):
        errors.append(f"contact.email doesn't look like an email address: {email!r}")
    if not str(dig(cfg, "contact", "phone", default="")).strip():
        warnings.append("contact.phone is empty - attendees will only see your email address.")

    sender = str(dig(cfg, "email", "sender_email", default="")).strip()
    if need("email.sender_email", sender) and not EMAIL_RE.match(sender):
        errors.append(f"email.sender_email doesn't look like an email address: {sender!r}")

    # price
    price = dig(cfg, "tickets", "price_usd")
    price_cents = None
    if price is None:
        errors.append("tickets.price_usd is empty - enter the ticket price in dollars, e.g. 65")
    else:
        try:
            price_cents = int(round(float(price) * 100))
            if price_cents < 50:
                errors.append("tickets.price_usd must be at least 0.50 (Stripe's minimum charge).")
        except (TypeError, ValueError):
            errors.append(f"tickets.price_usd must be a number like 65 or 65.50, got {price!r}.")

    # payments
    venmo = str(dig(cfg, "payments", "venmo_handle", default="")).strip()
    zelle = str(dig(cfg, "payments", "zelle_handle", default="")).strip()
    for label, val in (("payments.venmo_handle", venmo), ("payments.zelle_handle", zelle)):
        if val and not NO_SPACE_RE.match(val):
            errors.append(f"{label} must not contain spaces or line breaks: {val!r}")
        if val and "," in val:
            errors.append(f"{label} must not contain a comma: {val!r}")
    if not venmo and not zelle:
        warnings.append(
            "No Venmo or Zelle handle set. That is fine for a card-only site - just make sure "
            "you add the STRIPE_SECRET_KEY secret, otherwise attendees will have no way to pay."
        )

    # urls
    for label, val in (
        ("whatsapp_group_url", dig(cfg, "whatsapp_group_url", default="")),
        ("short_link", dig(cfg, "short_link", default="")),
        ("event.venue_maps_url", dig(cfg, "event", "venue_maps_url", default="")),
    ):
        val = str(val or "").strip()
        if val and not URL_RE.match(val):
            errors.append(f"{label} must start with https:// (or be left empty), got {val!r}")

    # form
    options = dig(cfg, "registration_form", "expectation_options", default=[])
    if not isinstance(options, list) or not (2 <= len(options) <= 8):
        errors.append("registration_form.expectation_options must be a list of 2 to 8 items.")
    elif any(not str(o).strip() or len(str(o)) > 100 for o in options):
        errors.append("Each registration_form.expectation_options item must be non-empty and under 100 characters.")

    # sample values guard (only enforced for real deploys)
    if strict and os.environ.get("PUNARMILAN_ALLOW_SAMPLE") != "1":
        if chapter_id == SAMPLE_CHAPTER_ID:
            errors.append("chapter_id is still the sample value 'sample-chapter' - choose your own (README step 3).")
        if email.endswith("@example.com") or sender.endswith("@example.com"):
            errors.append("contact.email / email.sender_email still use @example.com - put in your real addresses.")
        if "Sample" in str(dig(cfg, "contact", "name", default="")):
            errors.append("contact.name is still the sample value - put in the real contact person.")

    derived = None
    if event_date and not errors:
        weekday = event_date.strftime("%A")
        month = event_date.strftime("%B")
        derived = {
            "date_label": f"{weekday}, {month} {event_date.day}, {event_date.year}",
            "date_short": f"{event_date.strftime('%b')} {event_date.day}",
            "date_badge": {
                "month": event_date.strftime("%b").upper(),
                "day": str(event_date.day),
                "year": str(event_date.year),
            },
            "price_cents": price_cents,
            "venmo": venmo,
            "zelle": zelle,
        }
    return errors, warnings, derived


def check_assets(cfg, strict):
    errors, warnings = [], []
    venmo = str(dig(cfg, "payments", "venmo_handle", default="")).strip()
    zelle = str(dig(cfg, "payments", "zelle_handle", default="")).strip()
    for fname, needed in (("venmo-qr.png", bool(venmo)), ("zelle-qr.png", bool(zelle)), ("event-photo.jpg", False)):
        path = os.path.join(ASSETS_DIR, fname)
        if not os.path.exists(path):
            if needed:
                errors.append(f"assets/{fname} is missing but that payment method is switched on.")
            elif fname == "event-photo.jpg":
                errors.append("assets/event-photo.jpg is missing - add a photo for the top of the website.")
            continue
        is_placeholder = sha256(path) == PLACEHOLDER_HASHES.get(fname)
        if is_placeholder and needed and strict:
            errors.append(
                f"assets/{fname} is still the placeholder picture, but you set a handle for it. "
                "Replace it with a screenshot of your own QR code (README step 4), or clear the handle."
            )
        elif is_placeholder and fname == "event-photo.jpg":
            warnings.append("assets/event-photo.jpg is still the placeholder - swap in a real photo (README step 4).")
    return errors, warnings


def build_variables(cfg, derived):
    contact = cfg["contact"]
    short = str(cfg.get("short_link") or "").strip()
    price = derived["price_cents"] / 100
    price_text = f"${price:.0f}" if price == int(price) else f"${price:.2f}"
    return {
        "event_name": cfg["event"]["name"],
        "event_date": derived["date_label"],
        "event_date_short": derived["date_short"],
        "event_time": cfg["event"]["time"],
        "city": cfg["event"]["city"],
        "venue_name": cfg["event"]["venue_name"],
        "venue_address": cfg["event"]["venue_address"],
        "venue_maps_url": str(cfg["event"].get("venue_maps_url") or ""),
        "chapter_name": cfg["chapter_name"],
        "product_name": cfg["product_name"],
        "contact_name": contact["name"],
        "contact_title": contact["title"],
        "contact_phone": str(contact.get("phone") or contact["email"]),
        "contact_email": contact["email"],
        "ticket_price": price_text,
        "registration_link": short or "[your registration link]",
    }


def read_content(name, variables, errors):
    path = os.path.join(CONTENT_DIR, name)
    if not os.path.exists(path):
        errors.append(f"content/{name} is missing.")
        return ""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    text = chapter_config.strip_comments(raw)
    if "<!--" in text or "-->" in text:
        errors.append(
            f"content/{name} has a stray comment marker. A note to yourself must start with the "
            "characters <!-- and end with --> and must not contain either of those inside it."
        )
        return ""
    try:
        return chapter_config.fill_variables(text, variables)
    except KeyError as e:
        errors.append(
            f"content/{name} uses {{{e.args[0]}}}, which isn't a known placeholder. "
            f"Known ones: {', '.join('{' + k + '}' for k in sorted(variables))}"
        )
        return ""


def phone_tel(phone):
    digits = re.sub(r"[^\d+]", "", phone or "")
    return digits


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="validate only, write nothing")
    ap.add_argument("--strict", action="store_true", help="also refuse sample placeholder values")
    ap.add_argument("--get", metavar="KEY", help="print a single value: chapter_id")
    ap.add_argument("--sam-params", action="store_true", help="print Key=Value lines for sam deploy")
    args = ap.parse_args()

    cfg = load_config()

    if args.get:
        if args.get != "chapter_id":
            sys.exit("--get only supports: chapter_id")
        print(dig(cfg, "chapter_id", default=""))
        return

    errors, warnings, derived = validate(cfg, args.strict)
    a_err, a_warn = check_assets(cfg, args.strict)
    errors += a_err
    warnings += a_warn

    variables = build_variables(cfg, derived) if derived else None
    content = {}
    if variables:
        for key, fname in (("hero_blurb", "hero_blurb.md"), ("invite_email", "invite_email.md")):
            content[key] = read_content(fname, variables, errors)
        for fname in ("whatsapp_message.md", "linkedin_post.md"):
            content[fname] = read_content(fname, variables, errors)

    for w in warnings:
        print(f"  note: {w}", file=sys.stderr)
    if errors:
        print("\nchapter.config.yaml needs a few fixes before this can be built:\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(file=sys.stderr)
        sys.exit(1)

    if args.sam_params:
        # Blank optional values are left out so CloudFormation uses the template
        # default ("") - some CLI versions reject a `Key=` with nothing after it.
        print(f"TicketPriceCents={derived['price_cents']}")
        print(f"SenderEmail={cfg['email']['sender_email'].strip()}")
        if derived["venmo"]:
            print(f"VenmoHandle={derived['venmo']}")
        if derived["zelle"]:
            print(f"ZelleHandle={derived['zelle']}")
        return

    if args.check:
        print("chapter.config.yaml looks good.")
        return

    contact = cfg["contact"]
    event = {
        "name": cfg["event"]["name"],
        "date_label": derived["date_label"],
        "date_short": derived["date_short"],
        "date_badge": derived["date_badge"],
        "time_label": cfg["event"]["time"],
        "city_label": cfg["event"]["city"],
        "venue_name": cfg["event"]["venue_name"],
        "venue_address": cfg["event"]["venue_address"],
        "venue_maps_url": str(cfg["event"].get("venue_maps_url") or "").strip(),
    }
    contact_out = {
        "name": contact["name"].strip(),
        "title": contact["title"].strip(),
        "phone": str(contact.get("phone") or "").strip(),
        "phone_tel": phone_tel(str(contact.get("phone") or "")),
        "email": contact["email"].strip(),
    }
    form = {
        "expectation_options": [str(o).strip() for o in cfg["registration_form"]["expectation_options"]],
        "college_placeholder": str(cfg["registration_form"].get("college_placeholder") or "").strip(),
    }

    backend_cfg = {
        "chapter_id": cfg["chapter_id"],
        "product_name": cfg["product_name"],
        "chapter_name": cfg["chapter_name"],
        "event": event,
        "contact": contact_out,
        "whatsapp_group_url": str(cfg.get("whatsapp_group_url") or "").strip(),
        "content": {"invite_email": content["invite_email"]},
    }
    frontend_cfg = {
        "product_name": cfg["product_name"],
        "chapter_name": cfg["chapter_name"],
        "event": event,
        "contact": contact_out,
        "registration_form": form,
        "content": {"hero_blurb": content["hero_blurb"]},
    }
    write_json(os.path.join(ROOT, "backend-tickets", "chapter_config.json"), backend_cfg)
    write_json(os.path.join(ROOT, "frontend-tickets", "src", "chapter.generated.json"), frontend_cfg)

    # assets -> where the backend (emails) and frontend (website) look for them
    backend_assets = os.path.join(ROOT, "backend-tickets", "assets")
    frontend_assets = os.path.join(ROOT, "frontend-tickets", "src", "assets")
    os.makedirs(backend_assets, exist_ok=True)
    os.makedirs(frontend_assets, exist_ok=True)
    for fname in ("venmo-qr.png", "zelle-qr.png"):
        src = os.path.join(ASSETS_DIR, fname)
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(backend_assets, fname))
            shutil.copyfile(src, os.path.join(frontend_assets, fname))
    shutil.copyfile(os.path.join(ASSETS_DIR, "event-photo.jpg"), os.path.join(frontend_assets, "event-photo.jpg"))

    # drafts to copy/paste
    gen_dir = os.path.join(ROOT, "generated")
    os.makedirs(gen_dir, exist_ok=True)
    for src_name, out_name in (("whatsapp_message.md", "whatsapp_message.txt"), ("linkedin_post.md", "linkedin_post.txt")):
        with open(os.path.join(gen_dir, out_name), "w", encoding="utf-8") as f:
            f.write(content[src_name] + "\n")

    print(f"Prepared '{cfg['chapter_id']}': {event['name']}, {derived['date_label']}, {event['venue_name']}.")
    print("  wrote backend-tickets/chapter_config.json, frontend-tickets/src/chapter.generated.json, generated/*.txt")


if __name__ == "__main__":
    main()
