from __future__ import annotations

"""text_analytics.py

Self-contained helper functions for qualitative analysis of open-ended survey answers.
The module is intentionally framework-agnostic: it relies only on an active SQLAlchemy
session coming from the main Flask application (``app.db.session``).

Key points
----------
1. **No hard-coded JSON files** – answers are fetched from the database via the existing
   ``SurveyResponse``/``Question``/``QuestionType`` tables.
2. **Lightweight models** – uses ``sentence-transformers/all-MiniLM-L6-v2`` (22 MB) which is fast
   enough for CPU inference. If the host is truly resource-constrained, swap the encoder name for
   ``'paraphrase-MiniLM-L3-v2'`` (11 MB).
3. **Caching** – embeddings are persisted to ``embeddings/{hash}.npy`` so repeat runs are cheap.
4. **No CSV export** – results are returned as a ``pandas.DataFrame`` and can optionally be pushed
   into a dedicated table (see ``create_analysis_table``).
5. **Public helpers** – ``run_full_analysis`` and ``get_analysis`` can be imported directly by
   Flask routes (e.g. ``/api/reports/analytics/text``) or background tasks.

Dependencies (add to requirements.txt)
--------------------------------------
    sentence-transformers>=2.3.0
    nltk>=3.8.1
    bertopic>=0.16.0
    scikit-learn>=1.3.0
    pandas>=2.0.0
    beautifulsoup4>=4.12.0

Remember to run ``python -m nltk.downloader stopwords vader_lexicon`` once.
"""

from pathlib import Path
import hashlib
import json
from typing import List, Dict, Tuple, Iterable

import pandas as pd
from bs4 import BeautifulSoup
from nltk.corpus import stopwords  # type: ignore
from nltk.sentiment import SentimentIntensityAnalyzer  # type: ignore
from nltk import download as nltk_download  # type: ignore
from sentence_transformers import SentenceTransformer  # type: ignore
from sklearn.cluster import KMeans  # type: ignore
from bertopic import BERTopic  # type: ignore

# Database imports will be passed as parameters to avoid circular imports

# ---------------------------------------------------------------------------
# NLTK one-time setup (idempotent)
# ---------------------------------------------------------------------------
for pkg in ("stopwords", "vader_lexicon"):
    try:
        nltk_download(pkg, quiet=True)
    except Exception:  # pragma: no cover  # noqa: BLE001
        pass  # ignore network issues in production environments

STOPWORDS = set(stopwords.words("english"))
SIA = SentimentIntensityAnalyzer()

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_embedding_model: SentenceTransformer | None = None  # lazy loaded

EMBED_DIR = Path(__file__).with_suffix("").parent / "embeddings"
EMBED_DIR.mkdir(exist_ok=True)

OPEN_ENDED_TYPES = {"short_text", "paragraph"}

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _get_embedding_model() -> SentenceTransformer:  # noqa: D401
    """Lazily load the sentence-transformer model (global singleton)."""
    global _embedding_model  # noqa: PLW0603
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _embedding_model


def _clean_text(text: str) -> str:
    """Lower-case, strip HTML, remove stop-words; keep emojis/punctuation."""
    # Remove HTML
    text = BeautifulSoup(text, "html.parser").get_text(separator=" ")
    # Lower-case
    text = text.lower()
    # Tokenise quick & dirty
    tokens = [t for t in text.split() if t not in STOPWORDS]
    return " ".join(tokens)


def _sentiment_label(text: str) -> str:
    """Return 'positive', 'neutral', or 'negative' label using VADER compound score."""
    score = SIA.polarity_scores(text)["compound"]
    if score >= 0.05:
        return "positive"
    if score <= -0.05:
        return "negative"
    return "neutral"


def _persist_embeddings(texts: List[str]) -> Tuple[List[List[float]], Path]:
    """Compute sentence embeddings with caching based on sha1 of text list."""
    sha = hashlib.sha1("\n".join(texts).encode()).hexdigest()
    cache_path = EMBED_DIR / f"embeddings_{sha}.npy"
    if cache_path.exists():
        import numpy as np  # delayed import

        return np.load(cache_path), cache_path  # type: ignore[return-value]

    model = _get_embedding_model()
    embeds = model.encode(texts, convert_to_numpy=True, show_progress_bar=len(texts) > 100)
    import numpy as np  # type: ignore

    np.save(cache_path, embeds)
    return embeds, cache_path

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_open_ended_answers(db_session, survey_response_model, question_model) -> pd.DataFrame:  # noqa: D401
    """Pull *all* open-ended answers from the DB and return as DataFrame."""
    rows: List[Dict[str, str | int]] = []

    question_cache: Dict[int, Tuple[str, str]] = {}  # qid -> (type, text)

    responses: Iterable = db_session.query(survey_response_model).filter(
        survey_response_model.status == "completed"  # only finished surveys
    ).all()

    for resp in responses:
        # ``answers`` is stored as JSON – convert to dict if needed
        answer_dict: Dict[str, str] | None = (
            resp.answers if isinstance(resp.answers, dict) else json.loads(resp.answers or "{}")
        )
        if not answer_dict:
            continue

        for qid_str, answer in answer_dict.items():
            try:
                qid = int(qid_str)
            except ValueError:
                continue  # malformed key
            if not isinstance(answer, str) or not answer.strip():
                continue  # skip non-text answers

            if qid not in question_cache:
                q = db_session.query(question_model).get(qid)
                if not q:
                    continue
                qtype = q.type.name  # type: ignore[attr-defined]
                question_cache[qid] = (qtype, q.question_text)
            else:
                qtype, _ = question_cache[qid]

            if qtype not in OPEN_ENDED_TYPES:
                continue

            rows.append(
                {
                    "response_id": resp.id,
                    "question_id": qid,
                    "question_type": qtype,
                    "answer": answer.strip(),
                }
            )

    return pd.DataFrame(rows)


def run_full_analysis(db_session, survey_response_model, question_model, num_clusters: int = 10) -> pd.DataFrame:
    """Main entry – fetch answers, compute embeddings, sentiment, topics, clusters."""

    df = fetch_open_ended_answers(db_session, survey_response_model, question_model)
    if df.empty:
        raise ValueError("No open-ended answers found in database.")

    # Clean text
    df["clean_text"] = df["answer"].apply(_clean_text)

    # Sentiment
    df["sentiment"] = df["clean_text"].apply(_sentiment_label)

    # Embeddings (with caching)
    embeddings, _ = _persist_embeddings(df["clean_text"].tolist())

    # Topic modelling – BERTopic handles its own dimensionality reduction + clustering
    topic_model = BERTopic(embedding_model=_get_embedding_model(), calculate_probabilities=False)
    topics, _ = topic_model.fit_transform(df["clean_text"].tolist(), embeddings)
    df["topic"] = topics

    # K-means clustering on embeddings
    kmeans = KMeans(n_clusters=num_clusters, n_init="auto", random_state=42)
    df["cluster"] = kmeans.fit_predict(embeddings)

    return df


def get_analysis(db_session, survey_response_model, question_model, response_id: int) -> Dict[str, str | int]:
    """Return analysis dict for a *single* survey response (lazy compute fallback)."""
    global _analysis_cache  # noqa: PLW0603
    try:
        _analysis_cache
    except NameError:
        _analysis_cache = run_full_analysis(db_session, survey_response_model, question_model)  # type: ignore

    row = _analysis_cache[_analysis_cache["response_id"] == response_id].head(1)
    if row.empty:
        raise KeyError(f"Response {response_id} has no open-ended answers or is not completed.")
    return row.drop(columns=["clean_text"]).to_dict(orient="records")[0]

# ---------------------------------------------------------------------------
# Optional persistence helper
# ---------------------------------------------------------------------------

def create_analysis_table(db, db_session, survey_response_model, question_model) -> None:  # pragma: no cover
    """Create & populate a table named 'text_answer_analytics' if it does not exist."""
    from sqlalchemy import Column, Integer, String, JSON as SAJSON

    if db.engine.dialect.has_table(db.engine, "text_answer_analytics"):
        return

    class TextAnswerAnalytics(db.Model):  # type: ignore
        __tablename__ = "text_answer_analytics"
        id = Column(Integer, primary_key=True)
        response_id = Column(Integer)
        question_id = Column(Integer)
        sentiment = Column(String(20))
        topic = Column(Integer)
        cluster = Column(Integer)
        extra = Column(SAJSON)

    db.create_all()

    df = run_full_analysis(db_session, survey_response_model, question_model)
    df[[
        "response_id",
        "question_id",
        "sentiment",
        "topic",
        "cluster",
    ]].to_sql("text_answer_analytics", db.engine, if_exists="append", index=False)

__all__ = [
    "fetch_open_ended_answers",
    "run_full_analysis",
    "get_analysis",
]
