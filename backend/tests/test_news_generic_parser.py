"""Tests for news._parse_generic_page — Saudi Gazette / Arab News HTML parsing."""

from __future__ import annotations

from app.ingestion.scrapers.news import _parse_generic_page

_SAUDI_GAZETTE_SOURCE = {
    "key": "saudi_gazette",
    "display": "Saudi Gazette (Business)",
    "url": "https://saudigazette.com.sa/section/BUSINESS",
    "lang": "en",
}

_ARAB_NEWS_SOURCE = {
    "key": "arab_news",
    "display": "Arab News (Business)",
    "url": "https://www.arabnews.com/taxonomy/term/323",
    "lang": "en",
}

_RAW_URI = "local://test/page.html"


def _make_article_html(
    tag: str = "article",
    href: str = "/business/story-1234",
    title: str = "Riyadh warehouse rents rise 8% on logistics demand",
    date_str: str | None = "2025-06-08",
    css_class: str = "",
    include_date: bool = True,
) -> str:
    class_attr = f' class="{css_class}"' if css_class else ""
    date_block = ""
    if include_date and date_str:
        date_block = f'<time datetime="{date_str}">8 June 2025</time>'
    return f"""
    <html><body>
      <{tag}{class_attr}>
        <a href="{href}">{title}</a>
        {date_block}
      </{tag}>
    </body></html>
    """


class TestParseGenericPageBasic:
    def test_parses_article_tag(self):
        html = _make_article_html(tag="article")
        results = _parse_generic_page(html, _SAUDI_GAZETTE_SOURCE, _RAW_URI)
        assert len(results) == 1

    def test_parses_news_item_class(self):
        html = _make_article_html(tag="div", css_class="news-item")
        results = _parse_generic_page(html, _SAUDI_GAZETTE_SOURCE, _RAW_URI)
        assert len(results) == 1

    def test_parses_article_class(self):
        html = _make_article_html(tag="div", css_class="article")
        results = _parse_generic_page(html, _SAUDI_GAZETTE_SOURCE, _RAW_URI)
        assert len(results) == 1

    def test_title_captured_in_title_en(self):
        html = _make_article_html(title="MODON announces new industrial zone")
        results = _parse_generic_page(html, _SAUDI_GAZETTE_SOURCE, _RAW_URI)
        assert results[0]["title_en"] == "MODON announces new industrial zone"

    def test_title_captured_in_title_ar_for_arabic_source(self):
        ar_source = {
            "key": "argaam_ar",
            "display": "Argaam AR",
            "url": "https://www.argaam.com/ar/article/articlelist/tagid/193",
            "lang": "ar",
        }
        html = _make_article_html(title="تقرير السوق العقاري")
        results = _parse_generic_page(html, ar_source, _RAW_URI)
        assert results[0]["title_ar"] == "تقرير السوق العقاري"
        assert "title_en" not in results[0]

    def test_source_key_set_correctly(self):
        html = _make_article_html()
        results = _parse_generic_page(html, _ARAB_NEWS_SOURCE, _RAW_URI)
        assert results[0]["source"] == "arab_news"

    def test_external_id_from_href_slug(self):
        html = _make_article_html(href="/business/story-1234")
        results = _parse_generic_page(html, _SAUDI_GAZETTE_SOURCE, _RAW_URI)
        assert results[0]["external_id"] == "story-1234"

    def test_absolute_url_built_for_relative_href(self):
        html = _make_article_html(href="/business/story-1234")
        results = _parse_generic_page(html, _SAUDI_GAZETTE_SOURCE, _RAW_URI)
        assert results[0]["url"].startswith("https://saudigazette.com.sa")
        assert "story-1234" in results[0]["url"]

    def test_absolute_href_kept_as_is(self):
        html = _make_article_html(href="https://other.com/story-999")
        results = _parse_generic_page(html, _SAUDI_GAZETTE_SOURCE, _RAW_URI)
        assert results[0]["url"] == "https://other.com/story-999"

    def test_published_at_parsed_from_datetime_attr(self):
        html = _make_article_html(date_str="2025-06-08")
        results = _parse_generic_page(html, _SAUDI_GAZETTE_SOURCE, _RAW_URI)
        assert results[0]["published_at"] is not None
        assert results[0]["published_at"].year == 2025

    def test_published_at_none_when_no_date(self):
        html = _make_article_html(include_date=False)
        results = _parse_generic_page(html, _SAUDI_GAZETTE_SOURCE, _RAW_URI)
        assert results[0]["published_at"] is None

    def test_raw_uri_preserved(self):
        html = _make_article_html()
        results = _parse_generic_page(html, _SAUDI_GAZETTE_SOURCE, "local://mypage.html")
        assert results[0]["raw_uri"] == "local://mypage.html"

    def test_structured_facts_initialized_empty(self):
        html = _make_article_html()
        results = _parse_generic_page(html, _SAUDI_GAZETTE_SOURCE, _RAW_URI)
        assert results[0]["structured_facts"] == {}

    def test_relevance_score_initialized_none(self):
        html = _make_article_html()
        results = _parse_generic_page(html, _SAUDI_GAZETTE_SOURCE, _RAW_URI)
        assert results[0]["relevance_score"] is None


class TestParseGenericPageEdgeCases:
    def test_short_title_skipped(self):
        """Titles shorter than 10 chars are skipped."""
        html = _make_article_html(title="Short")
        results = _parse_generic_page(html, _SAUDI_GAZETTE_SOURCE, _RAW_URI)
        assert len(results) == 0

    def test_empty_html_returns_empty(self):
        results = _parse_generic_page("<html><body></body></html>", _SAUDI_GAZETTE_SOURCE, _RAW_URI)
        assert results == []

    def test_multiple_articles_parsed(self):
        html = """
        <html><body>
          <article>
            <a href="/story/001">Warehouse demand in Riyadh rises sharply</a>
          </article>
          <article>
            <a href="/story/002">MODON to develop new logistics zone in Riyadh</a>
          </article>
          <article>
            <a href="/story/003">Saudi real estate transactions hit record highs this quarter</a>
          </article>
        </body></html>
        """
        results = _parse_generic_page(html, _SAUDI_GAZETTE_SOURCE, _RAW_URI)
        assert len(results) == 3
        titles = [r["title_en"] for r in results]
        assert any("Warehouse" in t for t in titles)
        assert any("MODON" in t for t in titles)

    def test_no_href_skipped(self):
        html = """
        <html><body>
          <article>
            <span>Riyadh industrial rents see continued upward trend</span>
          </article>
        </body></html>
        """
        results = _parse_generic_page(html, _SAUDI_GAZETTE_SOURCE, _RAW_URI)
        assert len(results) == 0

    def test_h2_heading_parsed(self):
        """h2 tags are also parsed as article candidates."""
        html = """
        <html><body>
          <h2><a href="/story/h2-article">Logistics hubs attract major investment in Riyadh</a></h2>
        </body></html>
        """
        results = _parse_generic_page(html, _ARAB_NEWS_SOURCE, _RAW_URI)
        assert len(results) == 1
        assert "Logistics" in results[0]["title_en"]

    def test_h3_heading_parsed(self):
        """h3 tags are also parsed as article candidates."""
        html = """
        <html><body>
          <h3><a href="/story/h3-article">New REIT listings boost Riyadh market confidence</a></h3>
        </body></html>
        """
        results = _parse_generic_page(html, _ARAB_NEWS_SOURCE, _RAW_URI)
        assert len(results) == 1
