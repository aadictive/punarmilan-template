"""
chapter_config.py
Runtime access to this chapter's settings, plus the tiny text helpers shared by
the emails and by scripts/prepare.py.

The settings themselves live in chapter.config.yaml + content/*.md at the repo
root. scripts/prepare.py validates them and writes chapter_config.json next to
this file (it is git-ignored and regenerated on every deploy) so the Lambda
functions can read them with no extra dependencies.

Text helpers ("markdown-lite"): blank line = new paragraph, **bold**,
*italic*, [text](https://link). Everything else is HTML-escaped, so nobody
editing a content file can accidentally (or deliberately) inject markup.
"""
import html
import json
import os
import re

_PATH = os.environ.get("CHAPTER_CONFIG_PATH") or os.path.join(os.path.dirname(__file__), "chapter_config.json")
_cache = None


def get():
    global _cache
    if _cache is None:
        try:
            with open(_PATH, encoding="utf-8") as f:
                _cache = json.load(f)
        except FileNotFoundError:
            raise RuntimeError(
                "chapter_config.json is missing. Run `python3 scripts/prepare.py` before "
                "`sam build` (scripts/deploy.sh and the GitHub Action do this for you)."
            )
    return _cache


def reset_cache_for_tests():
    global _cache
    _cache = None


# ---------------------------------------------------------------- text helpers

_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_VAR_RE = re.compile(r"\{([a-z_]+)\}")
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)")


def strip_comments(text):
    return _COMMENT_RE.sub("", text).strip()


def fill_variables(text, variables):
    """Replace {name} with variables[name]. Unknown names raise KeyError so a
    typo like {evnt_name} is caught when the site is prepared, not shown to
    attendees."""

    def sub(m):
        key = m.group(1)
        if key not in variables:
            raise KeyError(key)
        return str(variables[key])

    return _VAR_RE.sub(sub, text)


def inline_html(text):
    escaped = html.escape(text, quote=True)
    escaped = _LINK_RE.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', escaped)
    escaped = _BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    escaped = _ITALIC_RE.sub(r"<em>\1</em>", escaped)
    return escaped


def paragraphs_html(text):
    """Markdown-lite text -> a run of <p>...</p> for use inside an email."""
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        block = block.strip()
        if not block:
            continue
        lines = [inline_html(line.strip()) for line in block.splitlines()]
        out.append("<p>" + "<br>".join(lines) + "</p>")
    return "\n".join(out)
