import asyncio

import httpx
import pytest

from app.research.analyzer import BlockedURLError, analyze_html, analyze_url, assert_public_host, normalize_url

GOOD_HTML = """<!doctype html><html lang="he"><head>
<title>מספרת דנה - תספורות בתל אביב</title>
<meta name="description" content="מספרה מקצועית בתל אביב. קבעו תור אונליין.">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta property="og:title" content="מספרת דנה">
<link rel="icon" href="/favicon.ico">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-1"></script>
<script type="application/ld+json">{"@type":"LocalBusiness"}</script>
</head><body><h1>מספרת דנה</h1>
<p>""" + "מילה " * 200 + """</p>
<a href="tel:031234567">התקשרו</a> <a href="https://wa.me/972501234567">וואטסאפ</a>
<a href="/about">אודות</a> <a href="/broken">שבור</a>
<button>קבעו תור עכשיו</button>
<img src="a.jpg" alt="המספרה"></body></html>"""

BAD_HTML = "<html><head></head><body><img src='x.jpg'><p>hello</p></body></html>"


def test_normalize_url():
    assert normalize_url("example.com") == "https://example.com"
    assert normalize_url(" http://a.co/x ") == "http://a.co/x"
    with pytest.raises(ValueError):
        normalize_url("")


@pytest.mark.parametrize("url", ["http://127.0.0.1", "http://localhost:8000", "http://10.0.0.5",
                                 "http://192.168.1.1/admin", "http://169.254.169.254/latest", "http://[::1]/"])
def test_blocks_private_addresses(url):
    with pytest.raises(BlockedURLError):
        assert_public_host(url)


def test_good_page_has_few_issues():
    facts, issues = analyze_html(GOOD_HTML, "https://dana.test/")
    ids = {i.id for i in issues}
    assert facts["phones"] == ["031234567"]
    assert facts["whatsapp_link"] is True
    assert "Google Analytics" in facts["tracking_tools"]
    assert any("קבעו" in c for c in facts["cta_texts"])
    assert not ids & {"no_title", "no_viewport", "no_contact", "no_cta", "no_tracking", "no_h1"}


def test_bad_page_flags_sales_problems():
    facts, issues = analyze_html(BAD_HTML, "https://bad.test/")
    ids = {i.id for i in issues}
    assert {"no_title", "no_meta_description", "no_h1", "no_viewport", "no_contact",
            "no_cta", "no_tracking", "img_alt", "thin_content"} <= ids
    for i in issues:  # כל בעיה חייבת הסבר עסקי והמלצה
        assert i.sales_impact and i.recommendation


def _transport():
    def handler(request: httpx.Request):
        path = request.url.path
        if path == "/":
            return httpx.Response(200, html=GOOD_HTML)
        if path in ("/about", "/robots.txt"):
            return httpx.Response(200, text="ok")
        return httpx.Response(404, text="not found")
    return httpx.MockTransport(handler)


def test_analyze_url_full_flow():
    rep = asyncio.run(analyze_url("https://dana.test/", allow_private=True, transport=_transport()))
    assert rep["ok"] is True
    assert rep["status_code"] == 200
    assert rep["facts"]["robots_txt"] is True
    assert rep["facts"]["sitemap_xml"] is False
    assert rep["facts"]["broken_links"] == ["https://dana.test/broken"]
    ids = [i["id"] for i in rep["issues"]]
    assert "broken_links" in ids and "no_sitemap" in ids
    assert 0 <= rep["score"] <= 100


def test_analyze_url_http_error():
    t = httpx.MockTransport(lambda r: httpx.Response(500))
    rep = asyncio.run(analyze_url("https://down.test/", allow_private=True, transport=t))
    assert rep["ok"] is False and rep["status_code"] == 500
    assert rep["issues"][0]["id"] == "http_error"


def test_analyze_url_blocks_internal():
    rep = asyncio.run(analyze_url("http://127.0.0.1:9/"))
    assert rep["ok"] is False and "פנימית" in rep["error"]


def test_redirect_to_internal_is_blocked():
    t = httpx.MockTransport(lambda r: httpx.Response(302, headers={"location": "http://127.0.0.1/"}))
    rep = asyncio.run(analyze_url("https://8.8.8.8/", transport=t))
    assert rep["ok"] is False and "פנימית" in rep["error"]
