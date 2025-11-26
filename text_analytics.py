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

def generate_question_label(question_text: str, max_words: int = 3) -> str:
    """
    Generate a concise 1-3 word label for a question using NLP.
    
    Args:
        question_text: The full question text
        max_words: Maximum number of words in the label (default: 3)
    
    Returns:
        A concise label (e.g., "Age Group", "Leadership Training", "Budget Status")
    """
    import re
    from nltk.corpus import stopwords
    
    # Ensure stopwords are downloaded
    try:
        stop_words = set(stopwords.words('english'))
    except:
        nltk_download('stopwords', quiet=True)
        stop_words = set(stopwords.words('english'))
    
    # Clean the question text
    text = question_text.lower()
    
    # Remove question marks and extra punctuation
    text = re.sub(r'[?!.,;:]', '', text)
    
    # Common question starters to remove
    question_starters = [
        'what is', 'what are', 'what kind of', 'what extent',
        'how many', 'how much', 'how long',
        'do you', 'does your', 'did you',
        'are you', 'is your', 'is this',
        'have you', 'has your',
        'when was', 'when did',
        'where is', 'where are',
        'which', 'who',
        'please', 'kindly'
    ]
    
    for starter in question_starters:
        if text.startswith(starter):
            text = text[len(starter):].strip()
    
    # Split into words
    words = text.split()
    
    # Remove stopwords but keep important ones
    important_words = []
    keep_words = {'years', 'year', 'many', 'much', 'long', 'old', 'new'}
    
    for word in words:
        if word not in stop_words or word in keep_words:
            # Skip very short words unless they're important
            if len(word) > 2 or word in keep_words:
                important_words.append(word)
    
    # Take first max_words important words
    label_words = important_words[:max_words]
    
    # Capitalize each word
    label = ' '.join(word.capitalize() for word in label_words)
    
    # Handle empty labels
    if not label:
        # Fallback: take first few words of original question
        fallback_words = question_text.split()[:max_words]
        label = ' '.join(word.capitalize() for word in fallback_words)
    
    return label


def generate_section_summary(questions: List[Dict]) -> str:
    """
    Generate a summary label for a section based on its questions using sentence embeddings.
    
    Args:
        questions: List of question dictionaries with 'question_text' field
    
    Returns:
        A summary label for the section (e.g., "Leadership & Training", "Institutional Resources")
    """
    if not questions:
        return "General Questions"
    
    # Extract all question texts
    question_texts = [q.get('question_text', '') for q in questions if q.get('question_text')]
    
    if not question_texts:
        return "General Questions"
    
    # Common themes to detect
    themes = {
        'Leadership': ['leader', 'president', 'board', 'manage', 'director', 'head'],
        'Training': ['training', 'education', 'degree', 'qualification', 'academic', 'formal'],
        'Resources': ['resource', 'support', 'available', 'help', 'software', 'system'],
        'Faculty': ['faculty', 'staff', 'teacher', 'professor', 'instructor'],
        'Students': ['student', 'enrollment', 'housing', 'learner'],
        'Infrastructure': ['electricity', 'water', 'solar', 'building', 'campus', 'facility'],
        'Financial': ['budget', 'dollar', 'funding', 'financial', 'cost', 'money'],
        'Personal': ['age', 'name', 'email', 'address', 'personal', 'contact'],
        'Institutional': ['institution', 'school', 'university', 'college', 'seminary'],
        'Accreditation': ['accredit', 'certification', 'quality', 'standard']
    }
    
    # Count theme occurrences
    theme_scores = {theme: 0 for theme in themes}
    
    combined_text = ' '.join(question_texts).lower()
    
    for theme, keywords in themes.items():
        for keyword in keywords:
            theme_scores[theme] += combined_text.count(keyword)
    
    # Get top 2 themes
    sorted_themes = sorted(theme_scores.items(), key=lambda x: x[1], reverse=True)
    top_themes = [theme for theme, score in sorted_themes[:2] if score > 0]
    
    if len(top_themes) >= 2:
        return f"{top_themes[0]} & {top_themes[1]}"
    elif len(top_themes) == 1:
        return top_themes[0]
    else:
        # Fallback: use first question's label
        return generate_question_label(question_texts[0], max_words=2)


# ---------------------------------------------------------------------------
# Question Classification (Database-Driven)
# ---------------------------------------------------------------------------

def classify_question_type(question_text: str, question_metadata: dict = None) -> dict:
    """
    Classify a question as numeric or non-numeric using question_type_id from database.
    Falls back to heuristic rules if question_type_id is not available.
    
    Args:
        question_text: The full question text
        question_metadata: Optional metadata including 'question_type_id'
    
    Returns:
        Dict with is_numeric, confidence, reasoning, method
    """
    # Try database-driven classification first
    if question_metadata and 'question_type_id' in question_metadata:
        result = _classify_by_question_type_id(question_metadata['question_type_id'])
        if result:
            return result
    
    # Fallback to heuristic classification
    return _classify_question_heuristic(question_text, question_metadata)


def _classify_by_question_type_id(question_type_id) -> dict:
    """
    Classify question as numeric/non-numeric based on question_type_id.
    
    Based on QUESTION_TYPE_REFERENCE.md:
    - IDs 1, 2, 9: Conditional (depends on content)
    - IDs 3, 5, 6: Non-numeric (yes/no, multi-select, paragraph)
    - IDs 4, 7, 8, 10: Numeric (likert, numeric, percentage, year_matrix)
    
    Args:
        question_type_id: The question type ID from question_types table
    
    Returns:
        Dict with classification or None if type is conditional
    """
    try:
        qtype_id = int(question_type_id)
    except (ValueError, TypeError):
        return None
    
    # Explicit numeric types
    if qtype_id == 4:  # likert5
        return {
            'is_numeric': True,
            'confidence': 0.95,
            'reasoning': 'Five-Point Likert Scale (ordinal 1-5)',
            'method': 'question_type_id',
            'question_type_id': qtype_id
        }
    
    if qtype_id == 7:  # numeric
        return {
            'is_numeric': True,
            'confidence': 0.98,
            'reasoning': 'Numeric Entry type',
            'method': 'question_type_id',
            'question_type_id': qtype_id
        }
    
    if qtype_id == 8:  # percentage
        return {
            'is_numeric': True,
            'confidence': 0.98,
            'reasoning': 'Percentage Allocation type',
            'method': 'question_type_id',
            'question_type_id': qtype_id
        }
    
    if qtype_id == 10:  # year_matrix
        return {
            'is_numeric': True,
            'confidence': 0.98,
            'reasoning': 'Year Matrix type (temporal numeric data)',
            'method': 'question_type_id',
            'question_type_id': qtype_id
        }
    
    # Explicit non-numeric types
    if qtype_id == 3:  # yes_no
        return {
            'is_numeric': False,
            'confidence': 0.95,
            'reasoning': 'Yes/No type (boolean/categorical)',
            'method': 'question_type_id',
            'question_type_id': qtype_id
        }
    
    if qtype_id == 5:  # multi_select
        return {
            'is_numeric': False,
            'confidence': 0.95,
            'reasoning': 'Multiple Select type (categorical)',
            'method': 'question_type_id',
            'question_type_id': qtype_id
        }
    
    if qtype_id == 6:  # paragraph
        return {
            'is_numeric': False,
            'confidence': 0.98,
            'reasoning': 'Paragraph Text type (long text)',
            'method': 'question_type_id',
            'question_type_id': qtype_id
        }
    
    # Conditional types (1=short_text, 2=single_choice, 9=flexible_input)
    # Return None to trigger heuristic analysis
    if qtype_id in [1, 2, 9]:
        return None
    
    # Unknown type ID
    return None


def _classify_question_heuristic(question_text: str, question_metadata: dict = None) -> dict:
    """
    Fallback heuristic-based classification when transformer is unavailable.
    
    Args:
        question_text: The full question text
        question_metadata: Optional metadata
    
    Returns:
        Dict with is_numeric, confidence, reasoning, method
    """
    import re
    
    qtext = question_text.lower()
    answer_type = ''
    input_type = ''
    options = []
    
    if question_metadata:
        answer_type = str(question_metadata.get('answer_type', '')).lower()
        input_type = str(question_metadata.get('input_type', '')).lower()
        options = question_metadata.get('options', [])
        if isinstance(options, str):
            try:
                import json
                options = json.loads(options)
            except:
                options = []
    
    # EXPLICIT NON-NUMERIC
    if 'textarea' in answer_type or 'textarea' in input_type:
        return {'is_numeric': False, 'confidence': 0.95, 'reasoning': 'Textarea field', 'method': 'heuristic'}
    
    if 'boolean' in input_type or 'bool' in answer_type or 'checkbox' in input_type:
        return {'is_numeric': False, 'confidence': 0.95, 'reasoning': 'Boolean/checkbox', 'method': 'heuristic'}
    
    if 'yes/no' in qtext or re.search(r'\byes\b.*\bno\b|\bno\b.*\byes\b', qtext):
        return {'is_numeric': False, 'confidence': 0.90, 'reasoning': 'Yes/No question', 'method': 'heuristic'}
    
    if options:
        lowered = [str(o).lower().strip() for o in options]
        if any(o in ['yes', 'no', 'true', 'false'] for o in lowered):
            return {'is_numeric': False, 'confidence': 0.90, 'reasoning': 'Yes/No options', 'method': 'heuristic'}
        
        # Check for scale terms
        scale_terms = ['strongly agree', 'agree', 'neutral', 'disagree', 'strongly disagree',
                      'very satisfied', 'satisfied', 'dissatisfied', 'very dissatisfied',
                      'excellent', 'good', 'fair', 'poor', 'very poor',
                      'always', 'often', 'sometimes', 'rarely', 'never']
        is_scale = any(any(term in opt for term in scale_terms) for opt in lowered)
        if is_scale:
            return {'is_numeric': True, 'confidence': 0.85, 'reasoning': 'Likert scale options', 'method': 'heuristic'}
        
        is_all_numeric = all(re.fullmatch(r"-?\d+(\.\d+)?", opt) for opt in lowered if opt)
        if is_all_numeric:
            return {'is_numeric': True, 'confidence': 0.95, 'reasoning': 'Pure numeric options', 'method': 'heuristic'}
    
    # POSITIVE SIGNALS
    numeric_tokens = ['number', 'numeric', 'integer', 'float', 'double', 'scale', 'rating', 
                     'range', 'slider', 'percent', 'percentage', 'age', 'count', 'amount',
                     'quantity', 'years', 'months', 'days', 'hours', 'how many', 'how much']
    token_str = ' '.join([answer_type, input_type, qtext])
    if any(tok in token_str for tok in numeric_tokens):
        return {'is_numeric': True, 'confidence': 0.75, 'reasoning': 'Contains numeric keywords', 'method': 'heuristic'}
    
    # Short text field - tentative
    if 'text' in answer_type and 'textarea' not in answer_type:
        return {'is_numeric': True, 'confidence': 0.50, 'reasoning': 'Short text field (tentative)', 'method': 'heuristic'}
    
    # Default
    return {'is_numeric': False, 'confidence': 0.60, 'reasoning': 'No numeric indicators', 'method': 'heuristic'}


__all__ = [
    "fetch_open_ended_answers",
    "run_full_analysis",
    "get_analysis",
    "generate_question_label",
    "generate_section_summary",
    "classify_question_type",
]
