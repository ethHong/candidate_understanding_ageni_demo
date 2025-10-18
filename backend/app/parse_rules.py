# backend/app/parse_rules.py
import re

MONTHS = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
DATE_SPAN = re.compile(
    rf"{MONTHS}\s+\d{{4}}\s*(?:–|-|to)\s*(?:Present|{MONTHS}\s+\d{{4}})", re.I
)

ACTION_VERBS = [
    "built",
    "developed",
    "launched",
    "designed",
    "created",
    "owned",
    "implemented",
    "delivered",
    "led",
    "analyzed",
    "optimized",
    "shipped",
    "deployed",
    "processed",
    "improved",
    "reduced",
    "increased",
    "orchestrated",
    "migrated",
    "established",
    "defined",
    "initiated",
    "measured",
    "automated",
]
ACTION_RX = re.compile(r"\b(" + "|".join(ACTION_VERBS) + r")\b", re.I)

METRIC_RX = re.compile(
    r"(\b\d{1,3}(?:\.\d+)?\s*%|\$\s?\d+(?:\.\d+)?\s?[KkMmBb]?|\b\d{1,4}\+?\b)", re.I
)
DELTA_RX = re.compile(
    r"(increase|improve|boost|raise|grow|reduce|cut|decrease|lower)\w*\s+(?:by\s+)?(\d{1,3}(?:\.\d+)?\s*%)",
    re.I,
)

TEAM_RX = re.compile(r"(?:team\s+of|cross[-\s]functional\s+team\s+of)\s+(\d+)", re.I)
LOCATION_RX = re.compile(
    r"([A-Za-z .,&-]+,\s*[A-Z]{2}|[A-Za-z .,&-]+\s*,\s*[A-Za-z .,&-]+)", re.I
)

TECH = {
    "sql",
    "python",
    "pyspark",
    "spark",
    "tableau",
    "power bi",
    "redash",
    "snowflake",
    "gcp",
    "aws",
    "neo4j",
    "mongodb",
    "postgresql",
    "airflow",
    "fastapi",
    "pytorch",
    "keras",
    "scikit-learn",
    "nlp",
    "bert",
    "transformer",
    "linux",
    "bash",
    "javascript",
    "html",
    "css",
}


def extract_stack(text: str):
    stack = []
    if "[" in text and "]" in text:
        inside = text[text.find("[") + 1 : text.rfind("]")]
        for t in re.split(r"[,/|]", inside):
            t = t.strip()
            if t:
                stack.append(t)
    low = text.lower()
    for t in TECH:
        if t in low:
            stack.append(t)
    norm, seen = [], set()
    for s in stack:
        key = s.strip().lower()
        if key and key not in seen:
            norm.append(s.strip())
            seen.add(key)
    return norm
