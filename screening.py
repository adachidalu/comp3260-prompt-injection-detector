"""A deliberately conservative boundary to Favour's future detection rules."""
import re
from .models import IncomingEmail, ScreeningDecision


def strict_unconfigured_detector(message: IncomingEmail) -> ScreeningDecision:
    """Fail closed until Favour's full detector is connected."""
    return ScreeningDecision('review', 'Full security detector is not connected')


def demo_detector(message: IncomingEmail) -> ScreeningDecision:
    """EDUCATIONAL DEMO ONLY. NOT the team's detector or evaluation result.

    Allows a simple plain-text example to flow; flags a trivial direct attack;
    sends HTML to review instead of pretending to understand every disguise.
    """
    match = re.search(
        r'ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|'
        r'(?:send|forward|reveal)\s+[^\n.]{0,60}(?:private|student\s+record)',
        message.inspection_text,
        flags=re.IGNORECASE,
    )
    if match:
        return ScreeningDecision('block', 'Demo rule found an instruction to override or disclose', match.group(0))
    if 'html' in message.content_type or '[MIME text/html]' in message.raw_body:
        return ScreeningDecision('review', 'Demo rule cannot certify HTML email', '<HTML email>')
    return ScreeningDecision('pass', 'Simple plain-text message passed the DEMO-only rules')
