from fakes import FakeEmbed
from seo_engine.text import mmr, ngram_candidates, passages, truncate_words


def test_ngram_candidates_skip_stopword_edges() -> None:
    cands = ngram_candidates("The client portal is great. A client portal for agencies.")
    assert cands[0] == "client portal"
    assert all(not c.startswith(("the ", "a ")) for c in cands)


def test_passages_respect_max_words() -> None:
    text = "\n".join(["word " * 50] * 5)
    out = passages(text, max_words=120)
    assert all(len(p.split()) <= 120 for p in out)
    assert sum(len(p.split()) for p in out) == 250


def test_mmr_prefers_diverse_items() -> None:
    e = FakeEmbed()
    doc, *cands = e.embed(
        ["client portal file sharing", "client portal", "client portals", "file sharing"]
    )
    chosen = mmr(doc, cands, top_n=2, diversity=0.7)
    assert 2 in chosen  # "file sharing" picked over the near-duplicate "client portals"


def test_truncate_words_keeps_paragraphs() -> None:
    text = "one two three\nfour five\nsix seven eight"
    assert truncate_words(text, 4) == "one two three\nfour"
    assert truncate_words(text, 100) == text
