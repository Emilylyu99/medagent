from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from app.models import GuidelineDocument, RetrievalHit

TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]", re.IGNORECASE)
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "before",
    "case",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "question",
    "should",
    "synthetic",
    "the",
    "to",
    "what",
    "with",
}


def tokenize(text: str) -> list[str]:
    return [token for token in TOKEN_PATTERN.findall(text.lower()) if token not in STOPWORDS]


class KnowledgeBase:
    """Small, auditable BM25 index suitable for the offline baseline."""

    def __init__(self, documents: list[GuidelineDocument]) -> None:
        if not documents:
            raise ValueError("The knowledge base must contain at least one document")
        self.documents = documents
        self._tokens = [tokenize(self._searchable_text(doc)) for doc in documents]
        self._term_frequencies = [Counter(tokens) for tokens in self._tokens]
        self._document_frequency = Counter(
            term for tokens in self._tokens for term in set(tokens)
        )
        self._average_length = sum(map(len, self._tokens)) / len(self._tokens)

    @classmethod
    def from_json(cls, path: Path) -> KnowledgeBase:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        documents = [GuidelineDocument.model_validate(item) for item in payload["documents"]]
        return cls(documents)

    @staticmethod
    def _searchable_text(document: GuidelineDocument) -> str:
        return " ".join(
            [
                document.title,
                document.category,
                document.text,
                document.recommendation,
                " ".join(document.keywords),
            ]
        )

    def search(self, query: str, top_k: int = 3) -> list[RetrievalHit]:
        query_terms = list(dict.fromkeys(tokenize(query)))
        scored: list[RetrievalHit] = []
        document_count = len(self.documents)
        k1 = 1.5
        b = 0.75

        for index, document in enumerate(self.documents):
            frequencies = self._term_frequencies[index]
            doc_length = len(self._tokens[index])
            score = 0.0
            matched: list[str] = []

            for term in query_terms:
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                matched.append(term)
                frequency_in_docs = self._document_frequency[term]
                inverse_document_frequency = math.log(
                    1 + (document_count - frequency_in_docs + 0.5) / (frequency_in_docs + 0.5)
                )
                denominator = frequency + k1 * (
                    1 - b + b * doc_length / self._average_length
                )
                score += inverse_document_frequency * frequency * (k1 + 1) / denominator

            keyword_tokens = set(tokenize(" ".join(document.keywords)))
            keyword_matches = keyword_tokens.intersection(query_terms)
            score += 0.35 * len(keyword_matches)
            matched.extend(term for term in keyword_matches if term not in matched)

            if score > 0:
                scored.append(
                    RetrievalHit(
                        document=document,
                        score=round(score, 4),
                        matched_terms=sorted(matched),
                    )
                )

        return sorted(scored, key=lambda hit: (-hit.score, hit.document.id))[:top_k]
