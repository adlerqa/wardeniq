"""The one stored vocabulary for a test case's priority: High, Medium, Low.

Each write path used its own: generation stored P1/P2/P3, the case editor
High/Medium/Low, sheet import High/Mid/Low. A CSV export then showed "P1" for a
generated case and "HIGH" for the same case after an edit (issue #174).
High/Medium/Low is what the editor offers and what the exports already map to.
"""

PRIORITIES = ("High", "Medium", "Low")

_ALIASES = {
    "high": "High", "h": "High", "critical": "High", "p0": "High", "p1": "High", "1": "High",
    "medium": "Medium", "mid": "Medium", "m": "Medium", "normal": "Medium", "p2": "Medium",
    "2": "Medium",
    "low": "Low", "l": "Low", "p3": "Low", "p4": "Low", "3": "Low",
}


def normalize_priority(value) -> str:
    """Map any known spelling to High/Medium/Low; empty or unknown -> Medium,
    the same default (P2/Mid) every write path already used."""
    return _ALIASES.get(str(value or "").strip().lower(), "Medium")


def legacy_priority_values() -> dict:
    """{stored spelling: canonical} for every known spelling that isn't canonical."""
    out = {}
    for alias, canon in _ALIASES.items():
        for spelling in {alias, alias.upper(), alias.title()}:
            if spelling != canon:
                out[spelling] = canon
    return out
