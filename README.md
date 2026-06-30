# AG Creator by Altay

AG Creator by Altay is a full-stack web application for creating groups of AI agents from a French natural-language brief, storing them in SQLite, and chatting with each agent while sharing context across the whole group.

The project is intentionally small enough to run locally, but structured like a real application:

- Vue 3 + Vite frontend
- Python FastAPI backend
- SQLite persistence
- Anthropic Messages API
- Docker Compose
- API access token
- backend-only AI provider key
- group-level shared conversation memory

## What The App Does

1. A user writes a French brief.
2. The backend asks the AI provider to return a strict JSON object containing one group and several specialized agents.
3. The backend stores the group and agents in SQLite.
4. The user selects a group, then an agent.
5. The user chats with the selected agent.
6. When an agent answers, the backend gives it:
   - its own system prompt;
   - its own recent conversation;
   - the recent messages from the other agents in the same group.
7. The response and the visible explanation are stored in SQLite.

This means agents in the same group are not isolated. They are aware of the group's recent conversation history through backend-controlled shared memory.

## Repository Structure

```text
.
├── backend
│   ├── Dockerfile
│   ├── app
│   │   ├── __init__.py
│   │   └── main.py
│   └── requirements.txt
├── frontend
│   ├── Dockerfile
│   ├── index.html
│   ├── package.json
│   ├── src
│   │   ├── App.vue
│   │   ├── main.js
│   │   └── styles.css
│   └── vite.config.js
├── docker-compose.yml
├── .env.example
└── README.md
```

## Local Setup With Docker

Copy the environment template:

```bash
cp .env.example .env
```

Generate a local API access token:

```bash
openssl rand -hex 32
```

Edit `.env`:

```bash
ANTHROPIC_API_KEY=your_anthropic_key
ANTHROPIC_MODEL=claude-sonnet-4-6
FRONTEND_ORIGIN=http://localhost:5173
DATABASE_URL=sqlite:///./data/ag_creator.sqlite3
AG_CREATOR_ACCESS_TOKEN=your_random_64_hex_token
```

Start the app:

```bash
docker compose --env-file .env up --build
```

Open:

- Frontend: http://localhost:5173
- Backend health: http://localhost:8000/health
- API docs: http://localhost:8000/docs

In the frontend, paste the same `AG_CREATOR_ACCESS_TOKEN` into the "Code d'acces API" field.

Stop the app:

```bash
docker compose down
```

## Local Setup Without Docker

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

## Environment Variables

| Variable | Required | Used By | Description |
| --- | --- | --- | --- |
| `ANTHROPIC_API_KEY` | Yes | Backend | Secret provider key. Never put it in the frontend. |
| `ANTHROPIC_MODEL` | Yes | Backend | Model name used for agent generation and chat. |
| `FRONTEND_ORIGIN` | Yes | Backend | Allowed browser origin for CORS. |
| `DATABASE_URL` | Yes | Backend | SQLite location, for example `sqlite:///./data/ag_creator.sqlite3`. |
| `AG_CREATOR_ACCESS_TOKEN` | Yes | Backend and user session | Local API access code sent as `X-AG-Creator-Token`. |

`.env` is ignored by Git. Do not commit real secrets.

## Security Model

### AI Provider Key

The Anthropic API key is only read by the backend:

```python
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
```

The Vue frontend never receives this key. It only calls the local FastAPI backend.

### API Access Token

Application routes are protected with a local access token:

```http
X-AG-Creator-Token: <AG_CREATOR_ACCESS_TOKEN>
```

The backend validates it with `hmac.compare_digest`, which avoids basic timing comparison issues:

```python
if not hmac.compare_digest(provided, AG_CREATOR_ACCESS_TOKEN):
    raise HTTPException(status_code=401, detail="Code d'acces API invalide ou manquant.")
```

The token is entered manually in the UI and stored in `sessionStorage`, not in Git and not in the frontend source.

### CORS

CORS is restricted to `FRONTEND_ORIGIN`:

```python
allow_origins=[FRONTEND_ORIGIN]
allow_methods=["GET", "POST", "DELETE", "OPTIONS"]
allow_headers=["Content-Type", "X-AG-Creator-Token"]
```

### Security Headers

Every response receives:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- `Cache-Control: no-store`

### Docker Security

The backend and frontend containers run with non-root users.

Docker Compose refuses to start unless these variables exist:

```yaml
ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY in .env}
AG_CREATOR_ACCESS_TOKEN: ${AG_CREATOR_ACCESS_TOKEN:?Set AG_CREATOR_ACCESS_TOKEN in .env}
```

SQLite data is stored in a Docker volume:

```yaml
volumes:
  - ag_creator_data:/app/data
```

## Database Schema

SQLite is initialized automatically at backend startup.

### `groups`

Stores one generated group:

- `id`
- `title`
- `summary`
- `source_instruction`
- `model`
- `created_at`

### `agents`

Stores agents linked to a group:

- `id`
- `group_id`
- `name`
- `role`
- `mission`
- `tools_json`
- `success_criteria_json`
- `system_prompt`
- `creation_reasoning`
- `source_instruction`
- `model`
- `created_at`

`group_id` uses `ON DELETE CASCADE`, so deleting a group deletes its agents.

### `messages`

Stores conversations per agent:

- `id`
- `agent_id`
- `role`
- `content`
- `visible_reasoning`
- `model`
- `created_at`

`agent_id` uses `ON DELETE CASCADE`, so deleting an agent deletes its messages.

## How Agent Groups Are Created

The endpoint `POST /api/agents/generate` receives:

```json
{
  "instruction": "Cree 4 agents pour analyser un besoin client SaaS.",
  "count": 4
}
```

The backend builds a prompt asking the provider for strict JSON:

```json
{
  "group": {
    "title": "short group title",
    "summary": "group objective"
  },
  "agents": [
    {
      "name": "agent name",
      "role": "clear role",
      "mission": "concrete mission",
      "tools": ["capability"],
      "success_criteria": ["criterion"],
      "system_prompt": "usable system prompt",
      "creation_reasoning": "public explanation"
    }
  ]
}
```

The backend parses the JSON, normalizes the fields, generates UUIDs, and inserts the group and agents into SQLite in one transaction.

## How Agents Share Group Context

Each direct chat still belongs to one selected agent. However, before calling the provider, the backend builds a shared group memory with recent messages from every agent in the same group:

```python
shared_context = group_conversation_context(db, agent["group_id"], agent_id)
```

That function joins `messages` with `agents`, filters by `agents.group_id`, and returns recent group messages like:

```text
- [time] other agent: Risk Analyst / Risk Analyst: ...
- [time] agent actif / User: ...
- [time] other agent: QA Agent / QA Agent: ...
```

The selected agent receives that shared memory in its system context:

```text
Memoire partagee du groupe:
...

Tu fais partie d'un groupe d'agents. Utilise la memoire partagee ci-dessus pour rester coherent avec les
echanges des autres agents du meme groupe.
```

This is how agents become aware of what other agents in their group have said. The frontend does not assemble this context; the backend does it, so the behavior is consistent and controlled.

## Visible Reasoning

The app stores a `visible_reasoning` field for assistant messages. This is a short public explanation of criteria, assumptions, and visible steps.

It is not hidden chain-of-thought. The app asks for useful explanation without exposing private internal reasoning.

## API Routes

### `GET /health`

Public health check. Returns model, database type, counts, and whether API access protection is enabled.

### `GET /api/groups`

Protected. Lists groups and their agents.

### `GET /api/groups/{group_id}`

Protected. Reads one group and its agents.

### `POST /api/agents/generate`

Protected. Creates a group and its agents.

### `GET /api/agents`

Protected. Lists all agents.

### `GET /api/agents/{agent_id}`

Protected. Reads one agent and its message history.

### `POST /api/agents/{agent_id}/chat`

Protected. Chats with one agent while injecting shared group memory.

### `DELETE /api/agents/{agent_id}`

Protected. Deletes one agent and its messages.

### `DELETE /api/groups/{group_id}`

Protected. Deletes a group, its agents, and their messages.

## Frontend Flow

`frontend/src/App.vue` owns the main user flow:

1. store the local API access code in `sessionStorage`;
2. call `/api/groups` to load groups;
3. call `/api/agents/generate` to create a group;
4. select a group and then an agent;
5. call `/api/agents/{agent_id}` to hydrate message history;
6. call `/api/agents/{agent_id}/chat` to continue a conversation;
7. call `DELETE` routes to remove agents or groups.

`frontend/src/styles.css` contains the responsive visual system. The UI is mobile-first but expands to a two-column desktop workspace.

## Backend Flow

`backend/app/main.py` contains the API and orchestration:

- `init_db()` creates and migrates SQLite tables.
- `require_api_access()` protects application routes.
- `require_claude()` blocks AI calls if the provider key is missing.
- `call_claude_for_group()` creates the group and agent definitions.
- `insert_group_with_agents()` persists generated data.
- `group_conversation_context()` builds shared memory across agents in the same group.
- `chat_with_agent()` stores the user message, injects shared memory, calls the provider, and stores the assistant answer.

## Development Checks

Backend syntax:

```bash
python3 -m py_compile backend/app/main.py
```

Frontend build:

```bash
cd frontend
npm run build
```

Docker config:

```bash
docker compose config
```

Secret scan:

```bash
rg -n "ghp_|gho_|sk-ant|ANTHROPIC_API_KEY=.*[A-Za-z0-9_-]{20,}" .
```

## Production Notes

This project is designed as a local/full-stack prototype. For production, add:

- real user authentication;
- HTTPS termination;
- request rate limiting;
- audit logging;
- managed secret storage;
- PostgreSQL instead of local SQLite if multiple users write concurrently;
- deployment-specific allowed hosts and CORS origins;
- backups for persistent data.

