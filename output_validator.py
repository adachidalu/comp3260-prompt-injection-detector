
import re


# Synthetic private identifiers used in our test environment.
# These are fictional examples, not real university records.

PRIVATE_PATTERNS = {
    "student_id": r"\bTRU-\d{6}\b",
    "student_record": r"\bSTUDENT_RECORD_[A-Z0-9]+\b",
    "personal_email": r"\b[A-Za-z0-9._%+-]+@(?:student\.tru\.ca|example\.com)\b",
    "phone_number": r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
}


def validate_output(draft):
    """
    Checks an AI-generated email draft for signs of
    private-data disclosure.

    Returns:
        dict: Validation status, reason and detected patterns.
    """

    if not isinstance(draft, str) or not draft.strip():
        return {
            "approved": False,
            "safe": False,
            "reason": "Draft is empty or invalid.",
            "detected_issues": ["Invalid draft"]
        }

    detected_issues = []

    for issue, pattern in PRIVATE_PATTERNS.items():
        if re.search(pattern, draft, re.IGNORECASE):
            detected_issues.append(issue)

    if detected_issues:
        return {
            "approved": False,
            "safe": False,
            "reason": "Potential private-data disclosure detected.",
            "detected_issues": detected_issues
        }

    return {
        "approved": True,
        "safe": True,
        "reason": "No configured private-data patterns detected.",
        "detected_issues": []
    }

