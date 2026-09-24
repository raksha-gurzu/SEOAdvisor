"""seo_snippet_check: title pixel width and description length (§5.5 checklist). Pure code."""

from pydantic import BaseModel

from seo_engine.config import Thresholds

# Arial/Helvetica advance widths in 1/1000 em (standard AFM metrics).
_WIDTHS: dict[str, int] = {
    " ": 278,
    "!": 278,
    '"': 355,
    "#": 556,
    "$": 556,
    "%": 889,
    "&": 667,
    "'": 191,
    "(": 333,
    ")": 333,
    "*": 389,
    "+": 584,
    ",": 278,
    "-": 333,
    ".": 278,
    "/": 278,
    ":": 278,
    ";": 278,
    "<": 584,
    "=": 584,
    ">": 584,
    "?": 556,
    "@": 1015,
    "[": 278,
    "\\": 278,
    "]": 278,
    "^": 469,
    "_": 556,
    "`": 333,
    "{": 334,
    "|": 260,
    "}": 334,
    "~": 584,
    "A": 667,
    "B": 667,
    "C": 722,
    "D": 722,
    "E": 667,
    "F": 611,
    "G": 778,
    "H": 722,
    "I": 278,
    "J": 500,
    "K": 667,
    "L": 556,
    "M": 833,
    "N": 722,
    "O": 778,
    "P": 667,
    "Q": 778,
    "R": 722,
    "S": 667,
    "T": 611,
    "U": 722,
    "V": 667,
    "W": 944,
    "X": 667,
    "Y": 667,
    "Z": 611,
    "a": 556,
    "b": 556,
    "c": 500,
    "d": 556,
    "e": 556,
    "f": 278,
    "g": 556,
    "h": 556,
    "i": 222,
    "j": 222,
    "k": 500,
    "l": 222,
    "m": 833,
    "n": 556,
    "o": 556,
    "p": 556,
    "q": 556,
    "r": 333,
    "s": 500,
    "t": 278,
    "u": 556,
    "v": 500,
    "w": 722,
    "x": 500,
    "y": 500,
    "z": 500,
    "–": 556,
    "—": 1000,
    "‘": 222,
    "’": 222,
    "“": 333,
    "”": 333,
    "…": 1000,
    "·": 278,
    "•": 350,
    "©": 737,
    "®": 737,
    "™": 1000,
}
_WIDTHS.update({str(d): 556 for d in range(10)})
_DEFAULT_WIDTH = 556
_WIDE_WIDTH = 1000  # CJK and other full-width characters


def _char_width(ch: str) -> int:
    if ch in _WIDTHS:
        return _WIDTHS[ch]
    if ord(ch) >= 0x2E80:
        return _WIDE_WIDTH
    return _DEFAULT_WIDTH


def pixel_width(text: str, font_px: int = 20) -> int:
    """Rendered width of `text` in Arial at `font_px`, rounded up."""
    units = sum(_char_width(ch) for ch in text)
    return -(-units * font_px // 1000)


class SnippetCheck(BaseModel):
    title: str
    title_px: int
    title_chars: int
    description_chars: int
    title_ok: bool
    description_ok: bool
    phrase_in_title: bool | None = None
    phrase_first_in_title: bool | None = None
    phrase_in_description_payoff: bool | None = None
    reasons: list[str]

    @property
    def passed(self) -> bool:
        return self.title_ok and self.description_ok and self.phrase_in_title is not False


def snippet_check(
    title: str, description: str, phrase: str | None = None, thresholds: Thresholds | None = None
) -> SnippetCheck:
    t = thresholds or Thresholds()
    title, description = " ".join(title.split()), " ".join(description.split())
    px = pixel_width(title, t.title_font_px)
    reasons: list[str] = []

    title_ok = t.title_min_chars <= len(title) and px <= t.title_max_px
    if px > t.title_max_px:
        reasons.append(f"title is {px}px, over {t.title_max_px}px; Google will truncate it")
    if len(title) < t.title_min_chars:
        reasons.append(f"title is {len(title)} chars, under {t.title_min_chars}; room left unused")

    d_len = len(description)
    description_ok = t.description_min_chars <= d_len <= t.description_max_chars
    if d_len > t.description_max_chars:
        reasons.append(f"description is {d_len} chars, over {t.description_max_chars}")
    if d_len < t.description_min_chars:
        reasons.append(f"description is {d_len} chars, under {t.description_min_chars}")

    in_title = first = in_payoff = None
    if phrase:
        p = phrase.lower()
        in_title = p in title.lower()
        first = title.lower().startswith(p)
        in_payoff = p in description[: t.description_payoff_chars].lower()
        if not in_title:
            reasons.append(f"phrase {phrase!r} not in title")
        elif not first:
            reasons.append(f"phrase {phrase!r} is not at the start of the title")
        if not in_payoff:
            reasons.append(
                f"phrase {phrase!r} not in first {t.description_payoff_chars} chars of description"
            )

    return SnippetCheck(
        title=title,
        title_px=px,
        title_chars=len(title),
        description_chars=d_len,
        title_ok=title_ok,
        description_ok=description_ok,
        phrase_in_title=in_title,
        phrase_first_in_title=first,
        phrase_in_description_payoff=in_payoff,
        reasons=reasons,
    )
