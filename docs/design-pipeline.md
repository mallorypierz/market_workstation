# Design pipeline and file map

Vue handles the screen. Python handles calculations. FastAPI provides the backend API carrying requests and results between them.

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Repository instructions for agents; currently empty. |
| `README.md` | Stack and project overview. |
| `frontend/` | Vue workspace and npm dependency manifests; no screen code yet. |
| `backend/` | Python workspace and pinned requirements; no application code yet. |
| `docs/design-pipeline.md` | File map and documentation workflow. |
| `docs/verification.md` | Repeatable checks and their current scope. |
| `prompts/01-setup.md` | Initial structure and stack prompt. |
| `prompts/02-documentation.md` | Documentation and handoff organization prompt. |
| `handoffs/current.md` | Current state, verification, and outstanding work for handoff. |

Record future major prompts in sequentially numbered files under `prompts/`. Update this map when the structure changes and update `docs/verification.md` when runnable checks become available. Refresh `handoffs/current.md` at each handoff so it describes the current state.

## Dependency setup additions

- `.gitignore`: excludes `.env`, `.venv/`, `node_modules/`, and Python bytecode.
- `backend/requirements.txt`: installed Python dependency versions for reproduction.
- `frontend/package.json`: Vue and Vite dependency declarations.
- `frontend/package-lock.json`: npm dependency lockfile.
- `prompts/03-dependency-check.md`: dependency inspection and approval requirement.
- `prompts/04-install-and-git.md`: installation approval and Git setup request.
- `prompts/05-connect-and-push.md`: connect the GitHub origin and push main.
