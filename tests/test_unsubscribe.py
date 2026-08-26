import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unsubscribe import parse_list_unsubscribe


def test_no_header_returns_none_method():
    result = parse_list_unsubscribe("", "")
    assert result["method"] is None


def test_http_without_one_click_post_header_is_not_auto_executed():
    # RFC 8058 one-click requires List-Unsubscribe-Post; without it, the
    # HTTP link might just load a page requiring further interaction —
    # must not be auto-POSTed as if it were one-click.
    result = parse_list_unsubscribe("<https://example.com/unsub?id=123>", "")
    assert result["method"] is None


def test_http_with_one_click_post_header_is_recognized():
    result = parse_list_unsubscribe(
        "<https://example.com/unsub?id=123>",
        "List-Unsubscribe=One-Click",
    )
    assert result["method"] == "http"
    assert result["target"] == "https://example.com/unsub?id=123"


def test_mailto_recognized_when_no_http_option():
    result = parse_list_unsubscribe("<mailto:unsub@example.com?subject=unsubscribe>", "")
    assert result["method"] == "mailto"
    assert result["target"] == "mailto:unsub@example.com?subject=unsubscribe"


def test_prefers_http_one_click_over_mailto_when_both_present():
    result = parse_list_unsubscribe(
        "<mailto:unsub@example.com>, <https://example.com/unsub>",
        "List-Unsubscribe=One-Click",
    )
    assert result["method"] == "http"


def test_malformed_header_does_not_crash():
    result = parse_list_unsubscribe("not a valid header at all", "")
    assert result["method"] is None
