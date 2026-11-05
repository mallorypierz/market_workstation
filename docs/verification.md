# Verification

Run these checks from the repository root after structural or documentation changes.

## Required directories and files

The following shell check prints any missing path and returns a nonzero status if a required path is missing:

```sh
(
  status_code=0
  for dir in frontend backend docs prompts handoffs; do
    if [ ! -d "$dir" ]; then
      echo "Missing directory: $dir"
      status_code=1
    fi
  done
  for file in AGENTS.md README.md docs/design-pipeline.md docs/verification.md prompts/01-setup.md prompts/02-documentation.md handoffs/current.md; do
    if [ ! -f "$file" ]; then
      echo "Missing file: $file"
      status_code=1
    fi
  done
  exit "$status_code"
)
```

## Documentation review

- Confirm README and the file map describe Vue for the screen, Python for calculations, and FastAPI for the backend API carrying requests and results.
- Confirm the file map matches the repository and local Markdown links resolve.
- Keep major prompts in sequentially numbered files and the current handoff up to date.
- Confirm local environments and `.env` files are excluded by Git.

## Application checks

Dependencies are installed, but no application code, build configuration, or automated tests exist yet. The npm-generated test script is a placeholder and is not a passing test suite.

Run from the repository root:

```sh
backend/.venv/bin/python -c 'import fastapi, uvicorn; print(fastapi.__version__, uvicorn.__version__)'
backend/.venv/bin/python -m pip check
node --version
npm --version
(cd frontend && npm ls --depth=0)
(cd frontend && node --input-type=module -e "import 'vue'; import 'vite'; import '@vitejs/plugin-vue'; console.log('Frontend imports OK')")
git rev-parse --show-toplevel
git branch --show-current
git check-ignore .env frontend/.env backend/.env backend/.venv/ frontend/node_modules/
git ls-files --others --exclude-standard
```

To reproduce dependencies in a fresh checkout (installation requires authorization):

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
(cd frontend && npm ci)
```
