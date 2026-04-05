"""Vector-match action text against RPG type descriptions for type selection."""

from __future__ import annotations

from pydantic import BaseModel

from memento.log import get_logger

logger = get_logger(__name__)

# Try sentence-transformers, fall back to word-overlap
_model = None


def _get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("TypeSelector using sentence-transformers")
        except ImportError:
            _model = "bow"
            logger.info("TypeSelector using bag-of-words fallback")
    return _model


def _embed(text: str) -> list[float]:
    model = _get_model()
    if model == "bow":
        return []  # BoW mode: return sentinel; select() uses _word_overlap instead
    return model.encode(text, normalize_embeddings=True).tolist()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    # With normalized embeddings, cosine similarity == dot product
    dot = sum(x * y for x, y in zip(a, b))
    if not a or not b:
        return 0.0
    # Clamp to [-1, 1] to handle floating point drift
    return max(-1.0, min(1.0, dot))


def _word_overlap(text_a: str, text_b: str) -> float:
    """Jaccard-like word overlap score for BoW fallback."""
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def _rescale(score: float) -> float:
    """Rescale cosine similarity from [-1, 1] to [0, 1] for intuitive thresholding.

    Raw cosine similarity between unrelated short texts typically lands in 0.1-0.3.
    Rescaling maps: -1 → 0.0, 0 → 0.5, 1 → 1.0, so a threshold of 0.3 means
    "somewhat similar" (raw ~-0.4) and 0.6 means "clearly related" (raw ~0.2).
    """
    return (score + 1.0) / 2.0


class TypeSelector:
    """Vector-match action text against RPG type descriptions."""

    def __init__(self, threshold: float = 0.3) -> None:
        self.threshold = threshold
        self.types: dict[str, type[BaseModel]] = {}
        self._embeddings: dict[str, list[float]] = {}
        self._raw_docs: dict[str, str] = {}

    def register(self, name: str, model: type[BaseModel]) -> None:
        """Register a type. Embeds the docstring + field descriptions for matching."""
        self.types[name] = model
        # Build a rich description: type name + docstring + field descriptions
        parts = [name]
        if model.__doc__:
            parts.append(model.__doc__.strip())
        for field_name, field_info in model.model_fields.items():
            if field_info.description:
                parts.append(f"{field_name}: {field_info.description}")
        desc = " ".join(parts)
        self._raw_docs[name] = desc
        self._embeddings[name] = _embed(desc)

    def select(self, action_text: str) -> list[str]:
        """Return type names whose descriptions are similar to the action.

        Scores are rescaled from [-1, 1] to [0, 1] so threshold semantics are:
        - 0.0: include everything
        - 0.3: lenient (over-include; safe for Graphiti which ignores non-matching types)
        - 0.6: strict (only clearly relevant types)
        """
        if not self._embeddings:
            return []

        using_bow = _get_model() == "bow"
        action_emb = _embed(action_text) if not using_bow else []

        selected = []
        for name, type_emb in self._embeddings.items():
            if using_bow:
                sim = _word_overlap(action_text, self._raw_docs[name])
            else:
                raw_sim = _cosine_similarity(action_emb, type_emb)
                sim = _rescale(raw_sim)
            if sim >= self.threshold:
                selected.append(name)
        return selected
