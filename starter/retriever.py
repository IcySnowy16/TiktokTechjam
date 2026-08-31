"""Hybrid retrieval: BM25 recall fused with attribute, phrase, TF-IDF, and personalization signals.

Stage weights live in config; a zero weight skips that stage's computation entirely,
which is how the milestones are enabled incrementally.
"""

from __future__ import annotations

from . import config
from .attribute_extractor import classify_text
from .catalog_store import CatalogStore, searchable_text
from .dialog_state import SessionState
from .personalization import preference_boost, rating_prior
from .text_utils import idf_coverage, tokenize


class HybridRetriever:
    def __init__(self, catalog: CatalogStore) -> None:
        self.catalog = catalog

    def rank(self, state: SessionState, top_k: int = 10) -> list[tuple[str, float]]:
        terms = self._query_terms(state)
        shortlist = self.catalog.bm25_search(terms, config.SHORTLIST_SIZE)
        if not shortlist:
            return []

        scores = dict(self._normalize(shortlist, config.W_BM25))
        slot_values = state.include_values()
        exclude_values = state.exclude_values()
        budget = state.budget_spec() if config.W_ATTR > 0 else None
        tags = state.user_profile.get("preference_tags") or []
        rating_style = str(state.user_profile.get("rating_style") or "")
        query_tokens = self._query_token_list(state) if config.W_TFIDF > 0 else []
        relax = state.relax_filters

        for asin in list(scores):
            doc_tokens = self.catalog.doc_tokens(asin)
            if config.W_PHRASE > 0 and slot_values:
                scores[asin] += config.W_PHRASE * self._phrase_score(slot_values, doc_tokens)
            if config.W_EXCLUDE > 0 and exclude_values:
                scores[asin] -= config.W_EXCLUDE * self._exclusion_violation(
                    exclude_values, doc_tokens
                )
            if config.W_CATEGORY > 0 and state.category_terms:
                scores[asin] += self._category_score(state, doc_tokens)
            if config.W_ATTR > 0 and (slot_values or budget is not None):
                scores[asin] += config.W_ATTR * self._attribute_score(
                    state, asin, doc_tokens, budget, relax
                )
            if config.W_TFIDF > 0 and query_tokens:
                scores[asin] += config.W_TFIDF * idf_coverage(
                    query_tokens, doc_tokens, self.catalog.idf
                )
            if config.W_PERSONAL > 0 and tags:
                product = self.catalog.get_product(asin)
                scores[asin] += config.W_PERSONAL * preference_boost(
                    doc_tokens, searchable_text(product).lower(), tags
                )
            if config.W_RATING > 0:
                scores[asin] += config.W_RATING * rating_prior(
                    self.catalog.get_product(asin), rating_style
                )

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return ranked

    # -- query construction ------------------------------------------------

    def _query_terms(self, state: SessionState) -> list[str]:
        """Cumulative positive query: category + active include values + recent
        messages - with every excluded token removed (raw messages would
        otherwise smuggle negated terms back in)."""
        terms: list[str] = list(state.category_terms)
        for attribute, values in state.slots.items():
            if attribute == "budget":
                continue  # operator text ("stay under $150"), not lexical evidence
            for value in values:
                if value.active and value.polarity == "include":
                    terms.extend(tokenize(value.text))
        for message in state.utterance_log[-2:]:
            terms.extend(tokenize(message))
        excluded = state.excluded_tokens()
        if excluded:
            terms = [term for term in terms if term not in excluded]
        return terms

    def _query_token_list(self, state: SessionState) -> list[str]:
        seen: dict[str, None] = {}
        for value in state.include_values():
            for token in tokenize(value.text):
                seen.setdefault(token, None)
        for token in state.category_terms:
            seen.setdefault(token, None)
        return list(seen)

    # -- stage scores ------------------------------------------------------

    @staticmethod
    def _normalize(shortlist: list[tuple[str, float]], weight: float) -> list[tuple[str, float]]:
        values = [score for _, score in shortlist]
        low, high = min(values), max(values)
        span = (high - low) or 1.0
        return [(asin, weight * (score - low) / span) for asin, score in shortlist]

    def _phrase_score(self, slot_values, doc_tokens: set[str]) -> float:
        """Stage C: idf-weighted coverage of each disclosed phrase in the candidate's text.

        Disclosed constraints are near-literal fragments of the target's own
        listing, so high coverage on a distinctive phrase is the strongest
        single signal in the system.
        """
        total_weight = 0.0
        accumulated = 0.0
        for value in slot_values:
            phrase_tokens = tokenize(value.text)
            if not phrase_tokens:
                continue
            coverage = idf_coverage(phrase_tokens, doc_tokens, self.catalog.idf)
            if coverage < config.PHRASE_MIN_COVERAGE:
                coverage = 0.0
            # Recency multiplies the CONTRIBUTION only — putting it in the
            # denominator too made it cancel exactly for a lone override value.
            recency = 1.3 if value.weight >= config.OVERRIDE_NEW_VALUE_WEIGHT else 1.0
            accumulated += value.weight * recency * coverage
            total_weight += value.weight
        return accumulated / total_weight if total_weight > 0 else 0.0

    def _category_score(self, state: SessionState, doc_tokens: set[str]) -> float:
        """Anchor ranking to WHAT the customer is shopping for. Without this, a
        flat bonus (e.g. budget satisfied) lets any cheap off-category item —
        a belt when they asked for shoes — outrank the category (demo-exposed)."""
        coverage = idf_coverage(state.category_terms, doc_tokens, self.catalog.idf)
        return config.W_CATEGORY * coverage

    def _exclusion_violation(self, exclude_values, doc_tokens: set[str]) -> float:
        """How strongly a candidate matches what the customer ruled OUT (0..1)."""
        worst = 0.0
        for value in exclude_values:
            phrase_tokens = tokenize(value.text)
            if not phrase_tokens:
                continue
            coverage = idf_coverage(phrase_tokens, doc_tokens, self.catalog.idf)
            if coverage >= config.EXCLUDE_COVERAGE_MIN and coverage > worst:
                worst = coverage
        return worst

    def _attribute_score(
        self,
        state: SessionState,
        asin: str,
        doc_tokens: set[str],
        budget,  # Budget | None (typed operators: min/max/range/target)
        relax: bool,
    ) -> float:
        """Stage B: soft match bonus / contradiction penalty per typed slot. Never a hard filter."""
        attributes = self.catalog.get_attributes(asin)
        score = 0.0
        penalty = 0.0 if relax else config.ATTR_CONTRADICT_PENALTY
        for attribute, values in state.slots.items():
            if attribute in ("feature", "other", "category", "brand", "budget"):
                continue
            wanted: set[str] = set()
            unwanted: set[str] = set()
            for value in values:
                if not value.active:
                    continue
                target = wanted if value.polarity == "include" else unwanted
                target.update(tokenize(value.text))
            vocabulary = self._vocab_for(attribute)
            wanted &= vocabulary
            unwanted &= vocabulary
            have = attributes.values_for(attribute)
            if unwanted & have:
                score -= penalty
            if not wanted:
                continue
            if wanted & have:
                score += config.ATTR_MATCH_BONUS
            elif have:
                score -= penalty
        if budget is not None:
            if attributes.price is None:
                score += config.UNKNOWN_PRICE_CREDIT * config.ATTR_MATCH_BONUS
            elif budget.satisfied(attributes.price):
                score += config.ATTR_MATCH_BONUS
            elif budget.violated(attributes.price):
                score -= penalty
        return score

    @staticmethod
    def _vocab_for(attribute: str) -> set[str]:
        from .vocab import COLORS, MATERIALS, SIZE_TERMS, STYLE_TERMS, USE_CASE_TERMS
        return {
            "material": MATERIALS,
            "color": COLORS,
            "size": SIZE_TERMS,
            "style": STYLE_TERMS,
            "use_case": USE_CASE_TERMS,
        }.get(attribute, set())
