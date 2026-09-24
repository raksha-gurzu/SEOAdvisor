"""Plain-code text helpers: passages, n-gram candidates, MMR selection."""

import re
from collections.abc import Sequence

from seo_engine.providers.embeddings import cosine

STOPWORDS = frozenset(
    """a about above after again against all am an and any are as at be because been before being
    below between both but by can could did do does doing down during each few for from further
    had has have having he her here hers herself him himself his how i if in into is it its itself
    just me more most my myself no nor not now of off on once only or other our ours ourselves out
    over own same she should so some such than that the their theirs them themselves then there
    these they this those through to too under until up very was we were what when where which
    while who whom why will with would you your yours yourself yourselves also get got us one
    many much may might must need via per etc every within without across""".split()
)
_WORD = re.compile(r"[a-z0-9][a-z0-9'+&.-]*[a-z0-9+]|[a-z0-9]")


def words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def ngram_candidates(text: str, min_n: int = 2, max_n: int = 4, limit: int = 200) -> list[str]:
    """Most frequent 2-4 word phrases that neither start nor end with a stopword."""
    counts: dict[str, int] = {}
    for sentence in re.split(r"[.!?\n;:()\[\]|]+", text.lower()):
        toks = _WORD.findall(sentence)
        for n in range(min_n, max_n + 1):
            for i in range(len(toks) - n + 1):
                gram = toks[i : i + n]
                if gram[0] in STOPWORDS or gram[-1] in STOPWORDS or any(t.isdigit() for t in gram):
                    continue
                key = " ".join(gram)
                counts[key] = counts.get(key, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [k for k, _ in ranked[:limit]]


def mmr(
    doc_vec: list[float],
    cand_vecs: Sequence[list[float]],
    top_n: int,
    diversity: float = 0.5,
) -> list[int]:
    """Maximal marginal relevance: indices of `top_n` relevant but mutually different items."""
    if not cand_vecs:
        return []
    relevance = [cosine(doc_vec, v) for v in cand_vecs]
    chosen = [max(range(len(cand_vecs)), key=relevance.__getitem__)]
    remaining = set(range(len(cand_vecs))) - set(chosen)
    while remaining and len(chosen) < top_n:

        def score(i: int) -> float:
            redundancy = max(cosine(cand_vecs[i], cand_vecs[j]) for j in chosen)
            return (1 - diversity) * relevance[i] - diversity * redundancy

        best = max(sorted(remaining), key=score)
        chosen.append(best)
        remaining.discard(best)
    return chosen


def truncate_words(text: str, max_words: int) -> str:
    """First `max_words` words of `text`, keeping its line breaks (paragraphs stay intact)."""
    kept: list[str] = []
    left = max_words
    for line in text.splitlines():
        if left <= 0:
            break
        tokens = line.split()
        kept.append(" ".join(tokens[:left]))
        left -= len(tokens)
    return "\n".join(kept)


def passages(text: str, max_words: int = 120) -> list[str]:
    """Split text into passages of at most ~max_words, keeping paragraphs together."""
    out: list[str] = []
    current: list[str] = []
    for para in (p.strip() for p in re.split(r"\n\s*\n|\n", text)):
        if not para:
            continue
        para_words = para.split()
        if current and len(current) + len(para_words) > max_words:
            out.append(" ".join(current))
            current = []
        while len(para_words) > max_words:
            out.append(" ".join(para_words[:max_words]))
            para_words = para_words[max_words:]
        current += para_words
    if current:
        out.append(" ".join(current))
    return out
