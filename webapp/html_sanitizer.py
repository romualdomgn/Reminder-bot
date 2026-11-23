import html
import re
from html.parser import HTMLParser

TAG_ALIASES: dict[str, str] = {
    "b": "b",
    "strong": "b",
    "i": "i",
    "em": "i",
    "u": "u",
    "ins": "u",
    "s": "s",
    "strike": "s",
    "del": "s",
    "code": "code",
    "tg-spoiler": "tg-spoiler",
}

_EMPTY_TAG_RE = re.compile(r"<(b|i|u|s|code|tg-spoiler)></\1>")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


class _TelegramHTMLSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.open_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_l = tag.lower()
        if tag_l == "br":
            self.parts.append("\n")
            return

        norm = TAG_ALIASES.get(tag_l)
        if not norm:
            return
        if "code" in self.open_stack or norm in self.open_stack:
            return

        self.open_stack.append(norm)
        self.parts.append(f"<{norm}>")

    def handle_endtag(self, tag: str) -> None:
        norm = TAG_ALIASES.get(tag.lower())
        if not norm or norm not in self.open_stack:
            return

        to_reopen: list[str] = []
        while self.open_stack:
            top = self.open_stack.pop()
            self.parts.append(f"</{top}>")
            if top == norm:
                break
            to_reopen.append(top)

        for reopen_tag in reversed(to_reopen):
            self.open_stack.append(reopen_tag)
            self.parts.append(f"<{reopen_tag}>")

    def handle_data(self, data: str) -> None:
        clean = data.replace("\u200b", "").replace("\r\n", "\n").replace("\r", "\n")
        if clean:
            self.parts.append(html.escape(clean, quote=False))

    def get_result(self) -> str:
        while self.open_stack:
            self.parts.append(f"</{self.open_stack.pop()}>")
        result = "".join(self.parts).strip()
        while True:
            collapsed = _EMPTY_TAG_RE.sub("", result)
            if collapsed == result:
                break
            result = collapsed
        return result


def strip_html_for_ui(raw_text: str) -> str:
    return html.unescape(_HTML_TAG_RE.sub("", raw_text or "")).replace("\u200b", "").strip()


def sanitize_telegram_html(raw_html: str) -> str:
    parser = _TelegramHTMLSanitizer()
    parser.feed(raw_html or "")
    parser.close()
    return parser.get_result()
