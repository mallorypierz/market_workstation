# Market Workstation

## Stack

- **Vue** handles the screen in `frontend/`.
- **Python** handles calculations in `backend/`.
- **FastAPI** provides the backend API, carrying requests and results between the Vue frontend and Python calculations.

## Structure

```text
frontend/  # Vue frontend
backend/   # Python backend with FastAPI
docs/      # File map and repeatable verification checks
prompts/   # Major prompts in numbered Markdown files
handoffs/  # Current state for handoff
```

The project has structure and installed dependencies, but no application code yet. Python dependencies are recorded in `backend/requirements.txt`; frontend dependencies are recorded in `frontend/package.json` and `frontend/package-lock.json`. Local environments (`backend/.venv` and `frontend/node_modules`) are ignored by Git.

See [the file map](docs/design-pipeline.md), [verification checks](docs/verification.md), and [current handoff](handoffs/current.md).
