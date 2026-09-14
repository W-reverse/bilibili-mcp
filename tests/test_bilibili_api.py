import os

import requests

os.environ.setdefault("SESSDATA", "test-session")

from bilibili_video_info_mcp import bilibili_api


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, content=b"", headers=None):
        self.status_code = status_code
        self._json = json_data
        self.content = content
        self.headers = headers or {}
        self.url = "https://fake"

    def json(self):
        if self._json is None:
            raise ValueError("no json body")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"{self.status_code} Client Error for url: {self.url}")
            error.response = self
            raise error


def view_payload(aid=111, cid=222, pages="default", code=0):
    if pages == "default":
        pages = [{"cid": cid, "page": 1}]
    data = {"aid": aid, "cid": cid, "pages": pages}
    return {"code": code, "data": data}


def install(monkeypatch, handler):
    """Route bilibili_api.requests.get through ``handler(url, params, headers, timeout)``."""
    calls = []

    def wrapped(url, params=None, headers=None, timeout=None, **kwargs):
        calls.append({"url": url, "params": params, "headers": headers or {}, "timeout": timeout})
        return handler(url, params, headers, timeout)

    monkeypatch.setattr(bilibili_api.requests, "get", wrapped)
    return calls


# --------------------------------------------------------------------------- #
# get_video_basic_info
# --------------------------------------------------------------------------- #

def test_view_primary_success(monkeypatch):
    calls = install(monkeypatch, lambda url, p, h, t: FakeResponse(200, view_payload(aid=1, cid=2)))
    assert bilibili_api.get_video_basic_info("BVTEST") == (1, 2, None)
    assert [c["url"] for c in calls] == [bilibili_api.API_GET_VIEW_INFO]


def test_view_falls_back_on_412(monkeypatch):
    def handler(url, params, headers, timeout):
        if url == bilibili_api.API_GET_VIEW_INFO:
            return FakeResponse(412, headers={"Content-Type": "text/html"}, content=b"<html>risk</html>")
        return FakeResponse(200, view_payload(aid=7, cid=8))

    calls = install(monkeypatch, handler)
    assert bilibili_api.get_video_basic_info("BVTEST") == (7, 8, None)
    assert [c["url"] for c in calls] == [bilibili_api.API_GET_VIEW_INFO, bilibili_api.API_GET_VIEW_INFO_WBI]
    assert all(c["timeout"] == bilibili_api.DEFAULT_TIMEOUT for c in calls)


def test_view_falls_back_on_403(monkeypatch):
    def handler(url, params, headers, timeout):
        if url == bilibili_api.API_GET_VIEW_INFO:
            return FakeResponse(403)
        return FakeResponse(200, view_payload(aid=9, cid=10))

    install(monkeypatch, handler)
    assert bilibili_api.get_video_basic_info("BVTEST") == (9, 10, None)


def test_view_fallback_also_fails_reports_status(monkeypatch):
    install(monkeypatch, lambda url, p, h, t: FakeResponse(412))
    aid, cid, error = bilibili_api.get_video_basic_info("BVTEST")
    assert aid is None and cid is None
    assert "412" in error["error"]
    assert bilibili_api.API_GET_VIEW_INFO_WBI in error["error"]


def test_view_business_error_not_masked(monkeypatch):
    install(monkeypatch, lambda url, p, h, t: FakeResponse(200, {"code": -400, "message": "bad"}))
    aid, cid, error = bilibili_api.get_video_basic_info("BVTEST")
    assert aid is None and cid is None
    assert error["error"] == "Failed to get video info"
    assert error["details"]["code"] == -400


def test_view_multi_page_selects_requested_page(monkeypatch):
    pages = [{"cid": 100, "page": 1}, {"cid": 200, "page": 2}]
    install(monkeypatch, lambda url, p, h, t: FakeResponse(200, view_payload(aid=5, cid=100, pages=pages)))
    assert bilibili_api.get_video_basic_info("BVTEST", page=2) == (5, 200, None)


def test_view_page_out_of_range_uses_default_cid(monkeypatch):
    pages = [{"cid": 100, "page": 1}]
    install(monkeypatch, lambda url, p, h, t: FakeResponse(200, view_payload(aid=5, cid=999, pages=pages)))
    assert bilibili_api.get_video_basic_info("BVTEST", page=5) == (5, 999, None)


def test_view_fallback_missing_fields(monkeypatch):
    def handler(url, params, headers, timeout):
        if url == bilibili_api.API_GET_VIEW_INFO:
            return FakeResponse(412)
        return FakeResponse(200, {"code": 0, "data": {"cid": 5}})  # no aid

    install(monkeypatch, handler)
    aid, cid, error = bilibili_api.get_video_basic_info("BVTEST")
    assert aid is None and cid is None
    assert "Missing aid/cid" in error["error"]


def test_view_fallback_timeout_reports_type(monkeypatch):
    def handler(url, params, headers, timeout):
        if url == bilibili_api.API_GET_VIEW_INFO:
            return FakeResponse(412)
        raise requests.Timeout("timed out")

    install(monkeypatch, handler)
    aid, cid, error = bilibili_api.get_video_basic_info("BVTEST")
    assert aid is None and cid is None
    assert "Timeout" in error["error"]


def test_view_data_not_dict_is_error(monkeypatch):
    install(monkeypatch, lambda url, p, h, t: FakeResponse(200, {"code": 0, "data": ["nope"]}))
    aid, cid, error = bilibili_api.get_video_basic_info("BVTEST")
    assert aid is None and cid is None
    assert error is not None and "Unexpected" in error["error"]


def test_view_pages_not_list_is_error(monkeypatch):
    install(monkeypatch, lambda url, p, h, t: FakeResponse(200, view_payload(pages="oops")))
    aid, cid, error = bilibili_api.get_video_basic_info("BVTEST")
    assert aid is None and cid is None
    assert error is not None and "pages" in error["error"].lower()


def test_view_page_entry_not_dict_is_error(monkeypatch):
    install(monkeypatch, lambda url, p, h, t: FakeResponse(200, view_payload(pages=[1, 2])))
    aid, cid, error = bilibili_api.get_video_basic_info("BVTEST")
    assert aid is None and cid is None
    assert error is not None and "page entry" in error["error"].lower()


def test_view_json_decode_error_is_error(monkeypatch):
    install(monkeypatch, lambda url, p, h, t: FakeResponse(200))  # json() raises ValueError
    aid, cid, error = bilibili_api.get_video_basic_info("BVTEST")
    assert aid is None and cid is None
    assert error is not None and "parse" in error["error"].lower()


# --------------------------------------------------------------------------- #
# get_danmaku
# --------------------------------------------------------------------------- #

def test_danmaku_success_returns_texts(monkeypatch):
    body = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b"<i><chatid>1</chatid><d p=\"1,1,25\">hello</d><d p=\"2,1,25\">world</d></i>"
    )
    install(monkeypatch, lambda url, p, h, t: FakeResponse(200, content=body, headers={"Content-Type": "text/xml"}))
    danmaku, error = bilibili_api.get_danmaku(1)
    assert danmaku == ["hello", "world"]
    assert error is None


def test_danmaku_412_is_error_not_empty(monkeypatch):
    install(monkeypatch, lambda url, p, h, t: FakeResponse(412, content=b"<html>risk</html>"))
    danmaku, error = bilibili_api.get_danmaku(1)
    assert danmaku == []
    assert error is not None and "412" in error["error"]


def test_danmaku_unexpected_root_is_error(monkeypatch):
    install(monkeypatch, lambda url, p, h, t: FakeResponse(200, content=b"<html><body>blocked</body></html>"))
    danmaku, error = bilibili_api.get_danmaku(1)
    assert danmaku == []
    assert error is not None and "Unexpected" in error["error"]


def test_danmaku_parse_error_is_error(monkeypatch):
    install(monkeypatch, lambda url, p, h, t: FakeResponse(200, content=b"not xml <<"))
    danmaku, error = bilibili_api.get_danmaku(1)
    assert danmaku == []
    assert error is not None and "parse" in error["error"].lower()


# --------------------------------------------------------------------------- #
# get_subtitles (credential safety + strict error handling)
# --------------------------------------------------------------------------- #

def _wbi(subtitles):
    return {"code": 0, "data": {"subtitle": {"subtitles": subtitles}}}


def test_subtitles_protocol_relative_url_download_without_sessdata(monkeypatch):
    sub_url = "//i0.example.com/sub.json"
    content = {"body": [{"content": "line1"}, {"content": "line2"}]}
    seen = {}

    def handler(url, params, headers, timeout):
        if url == bilibili_api.API_GET_SUBTITLE:
            return FakeResponse(200, _wbi([{"lan": "zh", "subtitle_url": sub_url}]))
        seen["headers"] = headers
        seen["url"] = url
        return FakeResponse(200, content)

    install(monkeypatch, handler)
    subtitles, error = bilibili_api.get_subtitles(1, 2)
    assert error is None
    assert subtitles == [{"lan": "zh", "content": ["line1", "line2"]}]
    assert "Cookie" not in seen["headers"]  # SESSDATA must not reach the CDN host
    assert seen["url"] == "https:" + sub_url


def test_subtitles_absolute_https_url_supported(monkeypatch):
    sub_url = "https://i0.example.com/abs.json"
    seen = {}

    def handler(url, params, headers, timeout):
        if url == bilibili_api.API_GET_SUBTITLE:
            return FakeResponse(200, _wbi([{"lan": "en", "subtitle_url": sub_url}]))
        seen["url"] = url
        seen["headers"] = headers
        return FakeResponse(200, {"body": [{"content": "hi"}]})

    install(monkeypatch, handler)
    subtitles, error = bilibili_api.get_subtitles(1, 2)
    assert error is None
    assert subtitles == [{"lan": "en", "content": ["hi"]}]
    assert seen["url"] == sub_url  # absolute https must not be mangled to https:https://
    assert "Cookie" not in seen["headers"]


def test_subtitles_missing_url_with_metadata_is_error(monkeypatch, capsys):
    calls = install(monkeypatch, lambda url, p, h, t: FakeResponse(200, _wbi([{"lan": "zh"}])))
    subtitles, error = bilibili_api.get_subtitles(1, 2)
    assert subtitles == []
    assert error is not None
    assert len(calls) == 1  # nothing else fetched


def test_subtitles_unsupported_scheme_is_error(monkeypatch):
    install(monkeypatch, lambda url, p, h, t: FakeResponse(200, _wbi([{"lan": "zh", "subtitle_url": "http://evil/x.json"}])))
    subtitles, error = bilibili_api.get_subtitles(1, 2)
    assert subtitles == []
    assert error is not None


def test_subtitles_content_http_failure_is_error_without_url_leak(monkeypatch, capsys):
    sub_url = "//i0.example.com/secret.json"

    def handler(url, params, headers, timeout):
        if url == bilibili_api.API_GET_SUBTITLE:
            return FakeResponse(200, _wbi([{"lan": "zh", "subtitle_url": sub_url}]))
        raise requests.ConnectionError("boom")

    install(monkeypatch, handler)
    subtitles, error = bilibili_api.get_subtitles(1, 2)
    out = capsys.readouterr().out
    assert subtitles == []
    assert error is not None
    assert "secret.json" not in out and sub_url not in out


def test_subtitles_content_json_failure_is_error(monkeypatch):
    def handler(url, params, headers, timeout):
        if url == bilibili_api.API_GET_SUBTITLE:
            return FakeResponse(200, _wbi([{"lan": "zh", "subtitle_url": "//i0.example.com/x.json"}]))
        return FakeResponse(200)  # json() raises ValueError

    install(monkeypatch, handler)
    subtitles, error = bilibili_api.get_subtitles(1, 2)
    assert subtitles == []
    assert error is not None and "parse" in error["error"].lower()


def test_subtitles_body_wrong_type_is_error(monkeypatch):
    def handler(url, params, headers, timeout):
        if url == bilibili_api.API_GET_SUBTITLE:
            return FakeResponse(200, _wbi([{"lan": "zh", "subtitle_url": "//i0.example.com/x.json"}]))
        return FakeResponse(200, {"body": "oops"})

    install(monkeypatch, handler)
    subtitles, error = bilibili_api.get_subtitles(1, 2)
    assert subtitles == []
    assert error is not None and "format" in error["error"].lower()


def test_subtitles_partial_group_failure_is_error(monkeypatch):
    groups = [
        {"lan": "zh", "subtitle_url": "//i0.example.com/ok.json"},
        {"lan": "en", "subtitle_url": "//i0.example.com/bad.json"},
    ]

    def handler(url, params, headers, timeout):
        if url == bilibili_api.API_GET_SUBTITLE:
            return FakeResponse(200, _wbi(groups))
        if url.endswith("ok.json"):
            return FakeResponse(200, {"body": [{"content": "ok"}]})
        raise requests.ConnectionError("boom")

    install(monkeypatch, handler)
    subtitles, error = bilibili_api.get_subtitles(1, 2)
    assert subtitles == []  # no partial success
    assert error is not None


def test_subtitles_business_error_distinct_from_empty(monkeypatch):
    install(monkeypatch, lambda url, p, h, t: FakeResponse(200, {"code": -404}))
    subtitles, error = bilibili_api.get_subtitles(1, 2)
    assert subtitles == []
    assert error is not None


def test_subtitles_empty_is_not_error(monkeypatch):
    install(monkeypatch, lambda url, p, h, t: FakeResponse(200, _wbi([])))
    subtitles, error = bilibili_api.get_subtitles(1, 2)
    assert subtitles == []
    assert error is None


def test_subtitles_data_not_dict_is_error(monkeypatch):
    install(monkeypatch, lambda url, p, h, t: FakeResponse(200, {"code": 0, "data": ["nope"]}))
    subtitles, error = bilibili_api.get_subtitles(1, 2)
    assert subtitles == []
    assert error is not None and "Unexpected" in error["error"]


def test_subtitles_subtitle_not_dict_is_error(monkeypatch):
    install(monkeypatch, lambda url, p, h, t: FakeResponse(200, {"code": 0, "data": {"subtitle": "nope"}}))
    subtitles, error = bilibili_api.get_subtitles(1, 2)
    assert subtitles == []
    assert error is not None and "Unexpected" in error["error"]
