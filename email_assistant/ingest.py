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

_MAX_EML_BYTES = 1024 * 1024
_MAX_PARTS = 20
_MAX_BODY_CHARS = 60000  # Prototype limit: fail closed on very large messages


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
    except (LookupError, UnicodeError, ValueError) as exc:
        raise ValueError('Cannot safely decode an email MIME part') from exc


def parse_eml(path: Path) -> IncomingEmail:
    """Return original and extracted versions without discarding HTML evidence."""
    path = Path(path)
    data = path.read_bytes()
    if len(data) > _MAX_EML_BYTES:
        raise ValueError(f'Message too large to inspect safely: {path.name}')
    msg = BytesParser(policy=policy.default).parsebytes(data)
    all_parts = list(msg.walk())
    if len(all_parts) > _MAX_PARTS or any(part.defects for part in all_parts):
        raise ValueError('Email has excessive or malformed MIME structure')
    if not str(msg.get('Subject', '')).strip():
        raise ValueError('Email subject missing')
    if not parseaddr(str(msg.get('From', '')))[1]:
        raise ValueError('Email sender missing')
    parts: list[tuple[str, str]] = []
    for part in all_parts:
        if part.is_multipart():
            continue
        if part.get_content_disposition() == 'attachment' or part.get_filename():
            raise ValueError('Attachments are outside the prototype scope')
        mime = part.get_content_type().lower()
        if mime not in ('text/plain', 'text/html'):
            raise ValueError(f'Unsupported MIME part: {mime}')
        body = _part_text(part)
        if '\ufffd' in body or len(body) > _MAX_BODY_CHARS:
            raise ValueError('Decoded email body invalid or oversized')
        parts.append((mime, body))
    if not parts or len(parts) > 2 or len({mime for mime, _ in parts}) != len(parts):
        raise ValueError('Missing, duplicated, or ambiguous email body parts')

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
    if not isinstance(message, dict):
        raise ValueError('Graph message must be a dictionary')
    if message.get('hasAttachments') is True:
        raise ValueError('Graph attachments are outside the prototype scope')
    body = message.get('body')
    if not isinstance(body, dict):
        raise ValueError('Graph message body is missing')
    raw = body.get('content')
    typ = str(body.get('contentType', '')).lower()
    if not isinstance(raw, str) or typ not in ('text', 'html') or len(raw) > _MAX_BODY_CHARS:
        raise ValueError('Graph body missing, oversized, or unsupported')
    mime = 'text/html' if typ == 'html' else 'text/plain'
    full, visible = _html_text(raw) if mime == 'text/html' else (raw, raw)
    sender = (((message.get('from') or {}).get('emailAddress') or {}).get('address')) or '(unknown)'
    source_id = message.get('id')
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError('Graph message id is missing')
    if not isinstance(message.get('subject'), str) or not message['subject'].strip():
        raise ValueError('Graph message subject is missing')
    if not isinstance(sender, str) or sender == '(unknown)':
        raise ValueError('Graph message sender is missing')
    return IncomingEmail(
        source_id=source_id,
        sender=sender,
        subject=str(message.get('subject') or '(no subject)'),
        raw_body=raw,
        inspection_text=raw + '\n' + full,
        student_text=visible,
        content_type=mime,
    )
