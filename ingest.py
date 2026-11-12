"""Read synthetic local .eml files or already-fetched Microsoft Graph JSON.

This module never logs into Outlook and never sends email.
"""
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from html.parser import HTMLParser
from pathlib import Path
import re

from .models import IncomingEmail

_MAX_EML_BYTES = 1024 * 1024  # Prototype limit: fail closed on very large messages


class _EmailHTMLParser(HTMLParser):
    """Extract ALL text for inspection, plus visible-ish text for drafting.

    CSS stylesheets and complex rendering are not supported. A detector MUST
    still examine raw HTML; this parser is not a security filter.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.all_text: list[str] = []
        self.shown_text: list[str] = []
        self._hidden: list[bool] = []
        self._ignored: list[bool] = []

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        style = re.sub(r'\s+', '', (data.get('style') or '').lower())
        is_hidden = (
            'hidden' in data
            or (data.get('aria-hidden') or '').lower() == 'true'
            or any(x in style for x in ('display:none', 'visibility:hidden', 'opacity:0'))
            or bool(self._hidden and self._hidden[-1])
        )
        is_ignored = tag.lower() in ('script', 'style') or bool(self._ignored and self._ignored[-1])
        self._hidden.append(is_hidden)
        self._ignored.append(is_ignored)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self._hidden:
            self._hidden.pop()
        if self._ignored:
            self._ignored.pop()

    def handle_data(self, data):
        if not data.strip() or (self._ignored and self._ignored[-1]):
            return
        self.all_text.append(data.strip())
        if not (self._hidden and self._hidden[-1]):
            self.shown_text.append(data.strip())


def _html_text(html: str) -> tuple[str, str]:
    parser = _EmailHTMLParser()
    parser.feed(html)
    parser.close()
    return ' '.join(parser.all_text), ' '.join(parser.shown_text)


def _part_text(part) -> str:
    try:
        return part.get_content()
    except (LookupError, UnicodeError, ValueError):
        raw = part.get_payload(decode=True) or b''
        return raw.decode('utf-8', errors='replace')


def parse_eml(path: Path) -> IncomingEmail:
    """Return original and extracted versions without discarding HTML evidence."""
    path = Path(path)
    data = path.read_bytes()
    if len(data) > _MAX_EML_BYTES:
        raise ValueError(f'Message too large to inspect safely: {path.name}')
    msg = BytesParser(policy=policy.default).parsebytes(data)
    parts: list[tuple[str, str]] = []
    for part in msg.walk():
        if part.is_multipart() or part.get_content_disposition() == 'attachment':
            continue
        mime = part.get_content_type().lower()
        if mime in ('text/plain', 'text/html'):
            parts.append((mime, _part_text(part)))
    if not parts:
        raise ValueError(f'No supported plain-text or HTML body: {path.name}')

    all_raw = '\n\n'.join(f'[MIME {mime}]\n{body}' for mime, body in parts)
    plain = next((body for mime, body in parts if mime == 'text/plain'), None)
    html = next((body for mime, body in parts if mime == 'text/html'), None)
    html_all, html_visible = _html_text(html) if html is not None else ('', '')
    # The detector sees markup AND extracted text; the assistant sees the plain
    # alternative (preferred) or visible-ish extracted HTML, only after PASS.
    inspection = '\n'.join(x for x in (all_raw, html_all) if x)
    student_text = plain if plain is not None else html_visible
    content_type = 'multipart/alternative' if len(parts) > 1 else parts[0][0]
    _, sender = parseaddr(str(msg.get('From', '')))
    return IncomingEmail(
        source_id=path.name,
        sender=sender or '(unknown)',
        subject=str(msg.get('Subject', '(no subject)')),
        raw_body=all_raw,
        inspection_text=inspection,
        student_text=student_text,
        content_type=content_type,
    )


def parse_graph_message(message: dict) -> IncomingEmail:
    """Normalize one *already fetched* Graph message (no API/auth here)."""
    body = message.get('body') or {}
    raw = body.get('content')
    if not isinstance(raw, str):
        raise ValueError('Graph message body is missing')
    mime = 'text/html' if str(body.get('contentType', '')).lower() == 'html' else 'text/plain'
    full, visible = _html_text(raw) if mime == 'text/html' else (raw, raw)
    sender = (((message.get('from') or {}).get('emailAddress') or {}).get('address')) or '(unknown)'
    source_id = str(message.get('id') or '')
    if not source_id:
        raise ValueError('Graph message id is missing')
    return IncomingEmail(
        source_id=source_id,
        sender=sender,
        subject=str(message.get('subject') or '(no subject)'),
        raw_body=raw,
        inspection_text=raw + '\n' + full,
        student_text=visible,
        content_type=mime,
    )
