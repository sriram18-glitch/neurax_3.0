"""Language safety and validation.

Every recommendation string is validated against forbidden causal/certainty
language. A recommendation that fails validation is rejected, not softened
silently. This is a hard gate, not a style guide.
"""

from __future__ import annotations

import re

FORBIDDEN_PATTERNS = [
    r"\bwill fix\b",
    r"\bwill increase\b",
    r"\bwill reduce\b",
    r"\bwill save\b",
    r"\bwill eliminate\b",
    r"\bguaranteed\b",
    r"\bproven cause\b",
    r"\bconfirmed root cause\b",
    r"\bis the root cause\b",
    r"\bguaranteed savings\b",
    r"\bdefinitely\b",
    r"\bwill definitely\b",
    r"\bensure[sd]? (?:a |an )?(?:increase|reduction|saving)",
]

PREFERRED_TERMS = [
    "investigate",
    "evaluate",
    "associated with",
    "candidate",
    "simulated",
    "under supplied assumptions",
    "the analysis indicates",
    "possible",
    "potential",
]

FORBIDDEN_ACTIONS = {
    "SET_SPEED",
    "SET_TEMPERATURE",
    "STOP_LINE",
    "CONTROL_MACHINE",
    "ADJUST_SETPOINT",
    "AUTOMATE",
}


NEGATION_PREFIXES = ("not ", "no ", "never ", "cannot be ", "can not be ", "isn't ", "wasn't ", "without ", "not yet ")


def find_violations(text: str) -> list[str]:
    """Find forbidden *positive* assertions.

    Negated disclaimers ("not guaranteed", "not proven cause") are allowed and
    in fact encouraged - they are how the system stays honest. Only positive
    claims are violations.
    """
    lowered = (text or "").lower()
    violations: list[str] = []
    for pattern in FORBIDDEN_PATTERNS:
        for match in re.finditer(pattern, lowered):
            prefix = lowered[max(0, match.start() - 16) : match.start()]
            if any(negation in prefix for negation in NEGATION_PREFIXES):
                continue
            violations.append(match.group(0))
    return violations


def validate_recommendation(recommendation: dict) -> list[str]:
    """Return a list of validation errors; empty means valid."""
    errors: list[str] = []
    if not recommendation.get("evidence"):
        errors.append("recommendation has no evidence")
    if recommendation.get("action_type") in FORBIDDEN_ACTIONS:
        errors.append(f"action_type '{recommendation.get('action_type')}' implies machine control and is not allowed")
    if (
        recommendation.get("evidence_quality") == "INSUFFICIENT_EVIDENCE"
        and not recommendation.get("data_requirement")
    ):
        errors.append("recommendation marked INSUFFICIENT_EVIDENCE must not be emitted unless it is a data requirement")
    text_fields = [
        recommendation.get("title", ""),
        recommendation.get("why", ""),
        recommendation.get("epistemic_status", ""),
    ]
    for evidence in recommendation.get("evidence", []):
        text_fields.append(str(evidence.get("statement", "")))
        text_fields.append(str(evidence.get("detail", "")))
    for limitation in recommendation.get("limitations", []):
        text_fields.append(str(limitation))
    for text in text_fields:
        violations = find_violations(text)
        if violations:
            errors.append(f"forbidden language {violations} in: {text[:80]}")
    return errors
