"""Hybrid offline retrieval over the chunked knowledge base.

Three additions over plain BM25, each fixing an observed failure:

1. Query expansion. Operators write "cheap interceptor"; the catalog says
   "attritable" and "expendable". Without a domain lexicon those queries
   miss the documents that answer them.
2. Section boosting. An economics query should prefer economics chunks.
3. MMR diversification. Plain top-k returned three chunks of the same
   system and crowded out the AOR and threat context the report needs.

Dependency-free and deterministic so it runs identically on air-gapped
NIPR and SIPR hosts.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Final

from .knowledge_base import Chunk
from .models import RetrievedDoc

BM25_K1: Final[float] = 1.5
BM25_B: Final[float] = 0.75
MMR_LAMBDA: Final[float] = 0.7
SECTION_BOOST: Final[float] = 1.35
TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")

STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "for",
        "with",
        "on",
        "by",
        "at",
        "is",
        "are",
        "be",
        "as",
        "from",
        "that",
        "this",
    }
)

EXPANSIONS: Final[dict[str, tuple[str, ...]]] = {
    "cheap": ("attritable", "expendable", "low", "cost", "affordable"),
    "cheapest": ("attritable", "expendable", "low", "cost"),
    "affordable": ("attritable", "expendable", "low", "cost"),
    "disposable": ("attritable", "expendable", "consumable", "single", "use"),
    "attritable": ("expendable", "consumable", "low", "cost", "mass", "produced"),
    "expendable": ("attritable", "consumable", "single", "use"),
    "mass": ("scale", "production", "volume", "magazine"),
    "swarm": ("saturation", "salvo", "magazine", "depth", "volume"),
    "saturation": ("swarm", "salvo", "magazine", "depth"),
    "exchange": ("economics", "cost", "defeat", "ratio", "attritable"),
    "economics": ("exchange", "cost", "ratio", "defeat"),
    "magazine": ("depth", "salvo", "production", "replenish", "rate"),
    "jammer": ("electronic", "warfare", "ew", "rf", "defeat"),
    "jamming": ("electronic", "warfare", "ew", "rf"),
    "interceptor": ("kinetic", "defeat", "effector", "intercept"),
    "shahed": ("owa", "one", "way", "attack", "loitering", "group", "3"),
    "owa": ("shahed", "one", "way", "attack"),
    "fpv": ("attritable", "quadcopter", "group", "1", "first", "person", "view"),
    "gps": ("gnss", "denied", "navigation"),
    "gnss": ("gps", "denied", "navigation"),
    "startup": ("nontraditional", "emerging", "vendor", "scaleup"),
    "emerging": ("startup", "nontraditional", "vendor", "development"),
    "por": ("program", "record", "exquisite", "baseline", "prime"),
    "lightweight": ("man", "packable", "portable", "low", "swap"),
    "portable": ("man", "packable", "lightweight", "low", "swap"),
}

SECTION_HINTS: Final[dict[str, tuple[str, ...]]] = {
    "economics": (
        "cost",
        "cheap",
        "exchange",
        "attritable",
        "expendable",
        "magazine",
        "price",
        "afford",
    ),
    "threat": ("threat", "shahed", "fpv", "group", "adversary", "enemy"),
    "environment": ("heat", "dust", "cold", "maritime", "jamming", "ew", "gps", "terrain"),
    "provenance": ("source", "confidence", "evidence", "verified", "proven", "unverified"),
    "mission": ("mission", "thread", "defense", "strike", "isr", "resupply"),
    "taxonomy": ("tier", "classification", "class", "category"),
}


def tokenize(text: str) -> tuple[str, ...]:
    """Lowercase, split on non-alphanumerics, and drop stopwords."""
    tokens: list[str] = TOKEN_PATTERN.findall(text.lower())
    return tuple(t for t in tokens if t not in STOPWORDS)


def expand_query(tokens: tuple[str, ...]) -> tuple[str, ...]:
    """Append domain synonyms so operator phrasing reaches catalog wording."""
    expanded: list[str] = list(tokens)
    for token in tokens:
        expanded.extend(EXPANSIONS.get(token, ()))
    return tuple(expanded)


def preferred_sections(tokens: tuple[str, ...]) -> frozenset[str]:
    """Infer which chunk sections the query is really asking about."""
    token_set: frozenset[str] = frozenset(tokens)
    hit: list[str] = [
        section for section, hints in SECTION_HINTS.items() if token_set & frozenset(hints)
    ]
    return frozenset(hit)


@dataclass(frozen=True)
class _IndexedChunk:
    """One corpus chunk with its precomputed term frequencies."""

    chunk: Chunk
    term_freq: dict[str, int]
    length: int


class HybridRetriever:
    """BM25 index with query expansion, section boosting, and MMR output."""

    def __init__(self, corpus: tuple[Chunk, ...]) -> None:
        indexed: list[_IndexedChunk] = []
        doc_freq: dict[str, int] = {}
        total_length: int = 0
        for chunk in corpus:
            tokens: tuple[str, ...] = tokenize(f"{chunk.title} {chunk.section} {chunk.text}")
            freq: dict[str, int] = {}
            for token in tokens:
                freq[token] = freq.get(token, 0) + 1
            for term in freq:
                doc_freq[term] = doc_freq.get(term, 0) + 1
            indexed.append(_IndexedChunk(chunk, freq, len(tokens)))
            total_length += len(tokens)
        self._chunks: tuple[_IndexedChunk, ...] = tuple(indexed)
        self._doc_freq: dict[str, int] = doc_freq
        self._avg_length: float = total_length / len(indexed) if indexed else 1.0

    def _idf(self, term: str) -> float:
        """Inverse document frequency with a floor at zero."""
        n_docs: int = len(self._chunks)
        n_term: int = self._doc_freq.get(term, 0)
        if n_term == 0:
            return 0.0
        return max(0.0, math.log((n_docs - n_term + 0.5) / (n_term + 0.5) + 1.0))

    def _bm25(self, entry: _IndexedChunk, terms: tuple[str, ...]) -> float:
        """BM25 score of one chunk against the expanded query terms."""
        score: float = 0.0
        norm: float = 1.0 - BM25_B + BM25_B * (entry.length / self._avg_length)
        for term in terms:
            tf: int = entry.term_freq.get(term, 0)
            if tf == 0:
                continue
            score += self._idf(term) * (tf * (BM25_K1 + 1.0)) / (tf + BM25_K1 * norm)
        return score

    def _candidates(self, query: str) -> list[RetrievedDoc]:
        """Score and section-boost every chunk with a nonzero match."""
        base: tuple[str, ...] = tokenize(query)
        if not base:
            return []
        terms: tuple[str, ...] = expand_query(base)
        wanted: frozenset[str] = preferred_sections(base)
        scored: list[RetrievedDoc] = []
        for entry in self._chunks:
            raw: float = self._bm25(entry, terms)
            if raw <= 0.0:
                continue
            boost: float = SECTION_BOOST if entry.chunk.section in wanted else 1.0
            scored.append(
                RetrievedDoc(
                    doc_id=entry.chunk.doc_id,
                    title=entry.chunk.title,
                    section=entry.chunk.section,
                    text=entry.chunk.text,
                    score=round(raw * boost, 4),
                )
            )
        scored.sort(key=lambda d: d.score, reverse=True)
        return scored

    def search(self, query: str, top_k: int = 8) -> tuple[RetrievedDoc, ...]:
        """Return top_k diversified results using iterative MMR selection."""
        if top_k <= 0:
            return ()
        pool: list[RetrievedDoc] = self._candidates(query)[: top_k * 4]
        if not pool:
            return ()
        selected: list[RetrievedDoc] = []
        seen_entities: dict[str, int] = {}
        while pool and len(selected) < top_k:
            best_index: int = 0
            best_value: float = -math.inf
            for index, doc in enumerate(pool):
                penalty: float = MMR_LAMBDA * seen_entities.get(doc.doc_id, 0)
                value: float = doc.score * (1.0 - min(penalty, 0.9))
                if value > best_value:
                    best_value = value
                    best_index = index
            chosen: RetrievedDoc = pool.pop(best_index)
            seen_entities[chosen.doc_id] = seen_entities.get(chosen.doc_id, 0) + 1
            selected.append(chosen)
        return tuple(selected)
