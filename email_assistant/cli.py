"""Local-only teaching CLI. Try: python -m chinaza_email.cli --detector demo"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone

from .drafting import MockDrafter, OpenAIDrafter
from .ingest import parse_eml, parse_graph_message
from .pipeline import process_message
from .models import ProcessingResult
from .screening import (
    demo_detector,
    full_detector,
    no_screening_detector,
    original_detector,
    strict_unconfigured_detector,
)

ROOT = Path(__file__).resolve().parent.parent


def save_sqlite(path: Path, records: list[dict]):
    with sqlite3.connect(path) as con:
        con.execute('''CREATE TABLE IF NOT EXISTS email_results (
            source_id TEXT, subject TEXT, verdict TEXT, reason TEXT,
            evidence TEXT, draft TEXT, provider TEXT, processed_at_utc TEXT)''')
        for r in records:
            con.execute('INSERT INTO email_results VALUES (?,?,?,?,?,?,?,?)',
                        (r['source_id'], r['subject'], r['verdict'], r['reason'],
                         r['evidence'], r['draft'], r['provider'], datetime.now(timezone.utc).isoformat()))


def main():
    p = argparse.ArgumentParser(description='Synthetic university email processing prototype')
    p.add_argument('--inbox', type=Path, default=ROOT / 'examples/inbox')
    p.add_argument('--graph-json', type=Path, help='Optional local JSON fixture with Graph message object(s)')
    p.add_argument('--policy', type=Path, default=ROOT / 'integration_test/mock_policy.txt')
    p.add_argument('--detector', choices=['strict', 'demo', 'none', 'original', 'full', 'favour'], default='full')
    p.add_argument('--provider', choices=['mock', 'openai'], default='mock')
    p.add_argument('--model', help='OpenAI model identifier; alternatively set OPENAI_MODEL')
    p.add_argument('--db', type=Path, help='Optional SQLite file to record outcomes')
    p.add_argument('--json-out', type=Path, help='Optional JSONL output for team integration')
    args = p.parse_args()

    policy_text = args.policy.read_text(encoding='utf-8')
    drafter = MockDrafter() if args.provider == 'mock' else OpenAIDrafter(args.model)
    if args.detector in ('full', 'favour'):
        detector = full_detector
    elif args.detector == 'original':
        detector = original_detector
    elif args.detector == 'none':
        detector = no_screening_detector
    elif args.detector == 'demo':
        detector = demo_detector
    else:
        detector = strict_unconfigured_detector
    messages = []
    intake_failures = []
    if args.inbox.exists():
        for path in sorted(args.inbox.glob('*.eml')):
            try:
                messages.append(parse_eml(path))
            except (OSError, ValueError) as exc:
                intake_failures.append(asdict(ProcessingResult(
                    path.name, '(unreadable message)', 'review',
                    f'Intake failed: {type(exc).__name__}', provider=drafter.name)))
    if args.graph_json:
        try:
            loaded = json.loads(args.graph_json.read_text(encoding='utf-8'))
            for i, item in enumerate(loaded if isinstance(loaded, list) else [loaded]):
                try:
                    messages.append(parse_graph_message(item))
                except (ValueError, AttributeError, TypeError) as exc:
                    intake_failures.append(asdict(ProcessingResult(
                        f'{args.graph_json.name}[{i}]', '(unreadable Graph message)',
                        'review', f'Intake failed: {type(exc).__name__}', provider=drafter.name)))
        except (OSError, ValueError) as exc:
            intake_failures.append(asdict(ProcessingResult(
                args.graph_json.name, '(invalid Graph fixture)', 'review',
                f'Intake failed: {type(exc).__name__}', provider=drafter.name)))
    if not messages and not intake_failures:
        raise SystemExit('No .eml or Graph fixture messages found')
    results = intake_failures + [asdict(process_message(m, detector=detector, drafter=drafter,
                                      policy_text=policy_text)) for m in messages]
    for r in results:
        print(f"{r['source_id']}: {r['verdict'].upper()} | {r['reason']}")
        if r['draft']:
            print('  Draft preview:', r['draft'].replace('\n', ' ')[:160])
    if args.db:
        save_sqlite(args.db, results)
    if args.json_out:
        args.json_out.write_text('\n'.join(json.dumps(r) for r in results) + '\n',
                                 encoding='utf-8')


if __name__ == '__main__':
    main()
