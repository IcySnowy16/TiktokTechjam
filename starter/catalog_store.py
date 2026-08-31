"""One-time catalog load: FTS5 BM25 index, document-frequency stats, lazy per-product caches."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter, OrderedDict
from pathlib import Path

from . import config
from .attribute_extractor import ProductAttributes, extract
from .text_utils import tokenize

_SEARCH_FIELDS = ("title", "features", "description", "categories", "details", "store")


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(f"{key} {item}" for key, item in value.items())
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


def searchable_text(product: dict) -> str:
    return " ".join(_text(product.get(field)) for field in _SEARCH_FIELDS).strip()


class CatalogStore:
    """In-memory catalog index. Built once in Agent.__init__, reused across all sessions."""

    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        self.catalog_path = Path(catalog_path)
        self.connection = sqlite3.connect(":memory:")
        self.products: dict[str, dict] = {}
        self._df: Counter[str] = Counter()
        self._doc_count = 0
        # LRU-bounded: only shortlist members are ever cached, but across many
        # sessions that would otherwise grow toward the whole 50k catalog.
        self._token_cache: OrderedDict[str, set[str]] = OrderedDict()
        self._attr_cache: OrderedDict[str, ProductAttributes] = OrderedDict()
        self._cache_cap = 20000
        self._build()

    # -- construction ------------------------------------------------------

    def _build(self) -> None:
        # Fail fast with actionable messages: a missing catalog or an sqlite
        # build without FTS5 should never surface as a mid-session mystery.
        if not self.catalog_path.is_file():
            raise FileNotFoundError(
                f"catalog not found at '{self.catalog_path}'. Download catalog.jsonl.gz "
                "from the participant-kit release, decompress, and place it there "
                "(see data/README.md); verify against SHA256SUMS."
            )
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                "CREATE VIRTUAL TABLE products USING fts5("
                "parent_asin UNINDEXED, title, categories, features, details, store, description, "
                "tokenize='unicode61 remove_diacritics 2')"
            )
        except sqlite3.OperationalError as error:
            raise RuntimeError(
                "this Python's sqlite3 lacks FTS5 support, which the agent requires"
            ) from error
        batch: list[tuple[str, str, str, str, str, str, str]] = []
        with self.catalog_path.open(encoding="utf-8") as handle:
            for line in handle:
                product = json.loads(line)
                asin = str(product["parent_asin"])
                self.products[asin] = product
                self._df.update(set(tokenize(searchable_text(product))))
                self._doc_count += 1
                batch.append(
                    (
                        asin,
                        _text(product.get("title")),
                        _text(product.get("categories")),
                        _text(product.get("features")),
                        _text(product.get("details")),
                        _text(product.get("store")),
                        _text(product.get("description")),
                    )
                )
                if len(batch) >= 1000:
                    cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
                    batch.clear()
        if batch:
            cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
        self.connection.commit()
        if not self.products:
            raise ValueError(f"catalog at '{self.catalog_path}' is empty")
        self.catalog_ids: frozenset[str] = frozenset(self.products)

    # -- lookups -----------------------------------------------------------

    def bm25_search(self, terms: list[str], limit: int = config.SHORTLIST_SIZE) -> list[tuple[str, float]]:
        """Top products for an OR-query of terms; returns (asin, relevance) with higher = better."""
        unique = list(dict.fromkeys(terms))[: config.MAX_QUERY_TERMS]
        expression = " OR ".join(f'"{term}"' for term in unique)
        if not expression:
            return []
        rows = self.connection.execute(
            "SELECT parent_asin, bm25(products, 0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0) "
            "FROM products WHERE products MATCH ? "
            "ORDER BY bm25(products, 0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0) LIMIT ?",
            (expression, limit),
        ).fetchall()
        # sqlite bm25() is lower-is-better (negative); flip so higher is better.
        return [(str(asin), -score) for asin, score in rows]

    def get_product(self, asin: str) -> dict:
        return self.products.get(asin, {})

    def doc_tokens(self, asin: str) -> set[str]:
        cached = self._token_cache.get(asin)
        if cached is None:
            cached = set(tokenize(searchable_text(self.products.get(asin, {}))))
            self._token_cache[asin] = cached
            if len(self._token_cache) > self._cache_cap:
                self._token_cache.popitem(last=False)
        else:
            self._token_cache.move_to_end(asin)
        return cached

    def get_attributes(self, asin: str) -> ProductAttributes:
        cached = self._attr_cache.get(asin)
        if cached is None:
            cached = extract(self.products.get(asin, {}), self.doc_tokens(asin))
            self._attr_cache[asin] = cached
            if len(self._attr_cache) > self._cache_cap:
                self._attr_cache.popitem(last=False)
        else:
            self._attr_cache.move_to_end(asin)
        return cached

    def idf(self, term: str) -> float:
        return math.log(self._doc_count / (1 + self._df.get(term, 0))) + 1.0
