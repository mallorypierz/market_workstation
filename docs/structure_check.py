"""Repeatable structure-only smoke check; no writes, installs, or live services."""
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    'README.md', 'AGENTS.md', 'docs/design-pipeline.md', 'docs/verification.md',
    'prompts/01-generic-project-startup.md',
    'handoffs/create-handoff.md', 'handoffs/current.md',
)


def main():
    failures = []
    for name in ('backend', 'frontend', 'docs', 'prompts', 'handoffs'):
        if not (ROOT / name).is_dir():
            failures.append(f'Missing directory: {name}')
    for name in REQUIRED_FILES:
        path = ROOT / name
        if not path.is_file():
            failures.append(f'Missing file: {name}')
            continue
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            if '://' not in target and not target.startswith('#'):
                if not (path.parent / target.split('#')[0]).exists():
                    failures.append(f'Broken local link in {name}: {target}')
    if failures:
        print('\n'.join(failures))
        return 1
    print(f'PASS: required structure and local Markdown links ({len(REQUIRED_FILES)} files).')
    print(f'Python {sys.version.split()[0]}: {sys.executable}')
    print(f'SQLite import OK: {sqlite3.sqlite_version}')
    print('NOT TESTED: application startup, browser UI, live feed, database persistence/replay.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
