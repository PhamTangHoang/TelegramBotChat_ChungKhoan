from app.data.news_text import sanitize_news_text


def test_sanitize_news_text_removes_html_and_decodes_entities() -> None:
    raw = "<div>Doanh thu <a href='https://example.test'>tăng &amp; tốt</a><br><br>Q3</div>"

    result = sanitize_news_text(raw)

    assert result == "Doanh thu tăng & tốt\nQ3"
    assert "<div>" not in result
    assert "<a" not in result


def test_sanitize_news_text_truncates_long_content() -> None:
    result = sanitize_news_text("<p>" + ("x" * 20) + "</p>", max_length=10)

    assert result == "xxxxxxxxxx"
