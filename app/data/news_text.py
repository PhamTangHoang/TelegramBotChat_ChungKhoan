from __future__ import annotations

from html.parser import HTMLParser


_BLOCK_TAGS = {
    "article",
    "br",
    "div",
    "h1",
    "h2",
    "h3",
    "li",
    "p",
    "section",
    "tr",
}
_IGNORED_TAGS = {"script", "style"}


class _NewsTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        normalized_tag = tag.lower()
        if normalized_tag in _IGNORED_TAGS:
            self._ignored_depth += 1
        elif self._ignored_depth == 0 and normalized_tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if self._ignored_depth == 0 and tag.lower() in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in _IGNORED_TAGS:
            self._ignored_depth = max(0, self._ignored_depth - 1)
        elif self._ignored_depth == 0 and normalized_tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            self.parts.append(data)


def sanitize_news_text(value: object, *, max_length: int | None = None) -> str:
    """Convert untrusted RSS HTML into bounded, readable plain text."""
    if max_length is not None and max_length < 1:
        raise ValueError("max_length must be positive")
    raw = str(value or "").strip()
    if not raw:
        return ""

    parser = _NewsTextParser()
    parser.feed(raw)
    parser.close()
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    cleaned = "\n".join(line for line in lines if line).strip()
    if max_length is not None:
        cleaned = cleaned[:max_length].rstrip()
    return cleaned
