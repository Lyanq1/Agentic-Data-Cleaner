import re
from app.tools.data.eda.models import UniqueRatioCategory

def _categorise_unique_ratio(ratio: float) -> UniqueRatioCategory:
    """Map a numeric unique_ratio to its semantic UniqueRatioCategory."""
    if ratio == 1.0:
        return UniqueRatioCategory.PRIMARY_KEY
    if ratio > 0.8:
        return UniqueRatioCategory.NEAR_UNIQUE
    if ratio > 0.2:
        return UniqueRatioCategory.REGULAR
    if ratio > 0.0:
        return UniqueRatioCategory.CATEGORICAL
    return UniqueRatioCategory.CONSTANT

# (pattern_name, compiled_regex, min_match_fraction_to_report)
_STRING_PATTERNS: list[tuple[str, re.Pattern[str], float]] = [
    ("uuid",         re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"), 0.8),
    ("email",        re.compile(r"^[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}$"), 0.8),
    ("url",          re.compile(r"^https?://\S+"), 0.8),
    ("date_iso",     re.compile(r"^\d{4}-\d{2}-\d{2}$"), 0.8),
    ("datetime_iso", re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"), 0.8),
    ("phone",        re.compile(r"^\+?[\d\s\-(]{7,20}$"), 0.7),
    ("zip_us",       re.compile(r"^\d{5}(-\d{4})?$"), 0.8),
    ("integer_str",  re.compile(r"^-?\d+$"), 0.8),
    ("float_str",    re.compile(r"^-?\d+\.\d+$"), 0.8),
    ("boolean_str",  re.compile(r"^(true|false|yes|no|1|0)$", re.IGNORECASE), 0.9),
    ("json_object",  re.compile(r"^\s*\{.*\}\s*$", re.DOTALL), 0.7),
    ("json_array",   re.compile(r"^\s*\[.*\]\s*$", re.DOTALL), 0.7),
]

def _detect_string_patterns(samples: list[str], threshold: float = 0.7) -> list[str]:
    """Return pattern names that match at least *threshold* fraction of *samples*."""
    if not samples:
        return []

    detected: list[str] = []
    n = len(samples)
    for pattern_name, regex, min_frac in _STRING_PATTERNS:
        matched = sum(1 for s in samples if regex.fullmatch(s) is not None)
        if matched / n >= min(threshold, min_frac):
            detected.append(pattern_name)
            break  # Take only the first (most specific) match to avoid over-tagging

    # If nothing matched yet, fall back to any pattern above the user threshold
    if not detected:
        for pattern_name, regex, _min_frac in _STRING_PATTERNS:
            matched = sum(1 for s in samples if regex.fullmatch(s) is not None)
            if matched / n >= threshold:
                detected.append(pattern_name)

    return detected
