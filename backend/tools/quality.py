import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports'
REPORTS.mkdir(exist_ok=True)

PY = sys.executable

CHECKS = [
    ('Ruff (lint)', [PY, '-m', 'ruff', 'check', '.']),
    ('Ruff (format)', [PY, '-m', 'ruff', 'format', '--check', '.']),
    ('Mypy', [PY, '-m', 'mypy', '--package', 'app']),
]


def run(name, cmd):
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    out = (p.stdout + '\n' + p.stderr).strip()
    return p.returncode, out


def main():
    results = []
    for name, cmd in CHECKS:
        code, out = run(name, cmd)
        log_name = name.lower().replace(' ', '_').replace('(', '').replace(')', '')
        (REPORTS / f'{log_name}.log').write_text(out, encoding='utf-8')
        results.append((name, code))

    print('\n=== Code Quality Report ===')
    failed = 0
    for name, code in results:
        ok = code == 0
        print(f'{"✅" if ok else "❌"} {name}')
        if not ok:
            failed += 1
            log_name = name.lower().replace(' ', '_').replace('(', '').replace(')', '')
            print(f'   ↳ see: reports/{log_name}.log')

    print('\nArtifacts:', str(REPORTS))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
