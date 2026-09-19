import pytest

import chapter_config as cc


def test_markdown_lite_renders_bold_italic_links_and_paragraphs():
    out = cc.paragraphs_html("Hi **bold** and *it*.\n\nSecond [link](https://x.org/?a=1&b=2) para\nnext line")
    assert out == (
        '<p>Hi <strong>bold</strong> and <em>it</em>.</p>\n'
        '<p>Second <a href="https://x.org/?a=1&amp;b=2">link</a> para<br>next line</p>'
    )


def test_markup_in_content_is_escaped_not_injected():
    out = cc.paragraphs_html('<script>alert(1)</script> & "quotes"')
    assert "<script>" not in out
    assert "&lt;script&gt;" in out and "&amp;" in out


def test_javascript_links_are_not_turned_into_anchors():
    out = cc.paragraphs_html("[click](javascript:alert(1))")
    assert "<a " not in out


def test_strip_comments_and_fill_variables():
    text = cc.strip_comments("<!-- note to self -->\nHello {name}!")
    assert text == "Hello {name}!"
    assert cc.fill_variables(text, {"name": "Sam"}) == "Hello Sam!"


def test_unknown_variable_is_reported():
    with pytest.raises(KeyError):
        cc.fill_variables("Hi {nmae}", {"name": "Sam"})
