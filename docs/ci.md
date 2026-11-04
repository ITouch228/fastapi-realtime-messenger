# CI / quality gates

GitHub Actions workflow: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

The workflow runs for pull requests, pushes to `main`, and manual dispatch.

| Job | Checks |
| --- | --- |
| Backend (Python 3.12) | Ruff lint + format, mypy, `unittest` discovery |
| Frontend (Node 22) | ESLint, Prettier |

## Running checks locally

From the repository root, after installing `backend/requirements-dev.txt` into
your Python environment and `npm ci` for the frontend dependencies:

```bash
cd backend
ruff check .
ruff format --check .
mypy --package app
python -m unittest discover -s tests -p "test_*.py" -v
cd ..
npx --yes --package eslint@9.39.2 eslint backend/app/static/js
npx --yes --package prettier@3.6.2 prettier --check "backend/app/static/**/*.{js,css,html}"
```

The initial CI has no database or Redis service containers. Unit tests must not
depend on running infrastructure; integration tests with PostgreSQL/Redis will
be added as a separate quality gate. On the base `main` branch, test discovery
may find zero tests until the first test-bearing PR is merged.

**Branch protection:** Require successful `Python 3.12 / lint, types, tests`
and `Node 22 / ESLint, Prettier` checks before merging pull requests.
Branch protection is configured in GitHub repository settings, not by this PR.

**Follow-up:** Add ESLint/Prettier to `package.json` and regenerate
`package-lock.json` so frontend tooling uses `npm exec` without downloading
CLIs on demand. Review and fix any pre-existing formatting issues surfaced by CI
rather than weakening the checks.
