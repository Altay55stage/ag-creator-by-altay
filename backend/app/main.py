import json
import hmac
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field

load_dotenv()

APP_NAME = "AG Creator by Altay"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6").strip()
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/ag_creator.sqlite3").strip()
AG_CREATOR_ACCESS_TOKEN = os.getenv("AG_CREATOR_ACCESS_TOKEN", "").strip()

app = FastAPI(
    title=f"{APP_NAME} API",
    description="Creation de groupes d'agents IA, conversation et stockage SQLite.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-AG-Creator-Token"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "0.0.0.0", "*.localhost"],
)

anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None


class GenerateAgentsRequest(BaseModel):
    instruction: str = Field(..., min_length=20, max_length=6000)
    count: int = Field(default=4, ge=1, le=8)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    return response


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sqlite_path() -> Path:
    if not DATABASE_URL.startswith("sqlite:///"):
        raise RuntimeError("DATABASE_URL doit utiliser le format sqlite:///chemin/fichier.sqlite3")
    raw_path = DATABASE_URL.replace("sqlite:///", "", 1)
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def connect_db() -> sqlite3.Connection:
    connection = sqlite3.connect(sqlite_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_db() -> None:
    with connect_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS groups (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                source_instruction TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                group_id TEXT,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                mission TEXT NOT NULL,
                tools_json TEXT NOT NULL,
                success_criteria_json TEXT NOT NULL,
                system_prompt TEXT NOT NULL,
                creation_reasoning TEXT NOT NULL,
                source_instruction TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                visible_reasoning TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_agent_created
            ON messages(agent_id, created_at);

            """
        )
        columns = {row["name"] for row in db.execute("PRAGMA table_info(agents)").fetchall()}
        if "group_id" not in columns:
            db.execute("ALTER TABLE agents ADD COLUMN group_id TEXT")
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_agents_group_created
            ON agents(group_id, created_at)
            """
        )


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def require_claude() -> Anthropic:
    if anthropic_client is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Le fournisseur IA n'est pas configure. Ajoute ANTHROPIC_API_KEY dans le fichier .env "
                "du backend ou dans les variables Docker."
            ),
        )
    return anthropic_client


def require_api_access(request: Request) -> None:
    if not AG_CREATOR_ACCESS_TOKEN:
        return
    provided = request.headers.get("X-AG-Creator-Token", "").strip()
    if not hmac.compare_digest(provided, AG_CREATOR_ACCESS_TOKEN):
        raise HTTPException(status_code=401, detail="Code d'acces API invalide ou manquant.")


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Le fournisseur IA n'a pas retourne de JSON exploitable.")
    return json.loads(cleaned[start : end + 1])


def text_from_claude_response(response: Any) -> str:
    return "".join(block.text for block in response.content if getattr(block, "type", "") == "text")


def group_from_row(row: sqlite3.Row, agents: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "summary": row["summary"],
        "source_instruction": row["source_instruction"],
        "model": row["model"],
        "created_at": row["created_at"],
        "agents": agents or [],
    }


def agent_from_row(row: sqlite3.Row, messages: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": row["id"],
        "group_id": row["group_id"],
        "name": row["name"],
        "role": row["role"],
        "mission": row["mission"],
        "tools": json.loads(row["tools_json"]),
        "success_criteria": json.loads(row["success_criteria_json"]),
        "system_prompt": row["system_prompt"],
        "creation_reasoning": row["creation_reasoning"],
        "source_instruction": row["source_instruction"],
        "model": row["model"],
        "created_at": row["created_at"],
        "messages": messages or [],
    }


def messages_for_agent(db: sqlite3.Connection, agent_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT id, role, content, visible_reasoning, model, created_at
        FROM messages
        WHERE agent_id = ?
        ORDER BY created_at ASC
        """,
        (agent_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def group_conversation_context(
    db: sqlite3.Connection,
    group_id: str | None,
    active_agent_id: str,
    limit: int = 24,
) -> str:
    if not group_id:
        return "Aucun contexte de groupe disponible."
    rows = db.execute(
        """
        SELECT
            messages.role,
            messages.content,
            messages.visible_reasoning,
            messages.created_at,
            agents.id AS agent_id,
            agents.name AS agent_name,
            agents.role AS agent_role
        FROM messages
        JOIN agents ON agents.id = messages.agent_id
        WHERE agents.group_id = ?
        ORDER BY messages.created_at DESC
        LIMIT ?
        """,
        (group_id, limit),
    ).fetchall()
    if not rows:
        return "Aucun autre echange dans ce groupe pour le moment."

    lines = []
    for row in reversed(rows):
        speaker = "Utilisateur" if row["role"] == "user" else row["agent_name"]
        scope = "agent actif" if row["agent_id"] == active_agent_id else f"autre agent: {row['agent_name']}"
        lines.append(f"- [{row['created_at']}] {scope} / {speaker}: {row['content']}")
        if row["visible_reasoning"]:
            lines.append(f"  Trace visible: {row['visible_reasoning']}")
    return "\n".join(lines)


def normalize_agent(raw: dict[str, Any], index: int, source_instruction: str, group_id: str) -> dict[str, Any]:
    name = str(raw.get("name") or raw.get("nom") or f"Agent {index + 1}").strip()
    role = str(raw.get("role") or "Specialiste IA").strip()
    mission = str(raw.get("mission") or "Executer une partie de la demande utilisateur.").strip()
    system_prompt = str(raw.get("system_prompt") or raw.get("prompt_systeme") or "").strip()
    creation_reasoning = str(
        raw.get("creation_reasoning")
        or raw.get("raisonnement_visible")
        or "Agent cree pour couvrir une responsabilite distincte de la demande."
    ).strip()

    if not system_prompt:
        system_prompt = (
            f"Tu es {name}, {role}. Ta mission: {mission}. "
            "Reponds en francais, de maniere concise, structuree et actionnable."
        )

    return {
        "id": str(uuid.uuid4()),
        "group_id": group_id,
        "name": name,
        "role": role,
        "mission": mission,
        "tools": [str(item) for item in raw.get("tools", raw.get("outils", []))][:8],
        "success_criteria": [
            str(item) for item in raw.get("success_criteria", raw.get("criteres_succes", []))
        ][:8],
        "system_prompt": system_prompt,
        "creation_reasoning": creation_reasoning,
        "created_at": now_iso(),
        "source_instruction": source_instruction,
        "model": ANTHROPIC_MODEL,
        "messages": [],
    }


def insert_group_with_agents(group: dict[str, Any], agents: list[dict[str, Any]]) -> None:
    with connect_db() as db:
        db.execute(
            """
            INSERT INTO groups (id, title, summary, source_instruction, model, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                group["id"],
                group["title"],
                group["summary"],
                group["source_instruction"],
                group["model"],
                group["created_at"],
            ),
        )
        db.executemany(
            """
            INSERT INTO agents (
                id, group_id, name, role, mission, tools_json, success_criteria_json,
                system_prompt, creation_reasoning, source_instruction, model, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    agent["id"],
                    agent["group_id"],
                    agent["name"],
                    agent["role"],
                    agent["mission"],
                    json.dumps(agent["tools"], ensure_ascii=True),
                    json.dumps(agent["success_criteria"], ensure_ascii=True),
                    agent["system_prompt"],
                    agent["creation_reasoning"],
                    agent["source_instruction"],
                    agent["model"],
                    agent["created_at"],
                )
                for agent in agents
            ],
        )


def call_claude_for_group(instruction: str, count: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    client = require_claude()
    group_id = str(uuid.uuid4())
    prompt = f"""
Tu es un architecte senior d'agents IA.
L'utilisateur decrit un besoin en francais. Cree un groupe contenant exactement {count} agents complementaires.

Contraintes:
- le groupe doit avoir un titre court et une synthese claire;
- chaque agent doit avoir une responsabilite claire et non redondante;
- les prompts systeme doivent etre directement utilisables pour converser avec l'agent;
- chaque prompt systeme doit rappeler que l'agent fait partie d'un groupe et doit tenir compte de la memoire partagee fournie par le backend;
- creation_reasoning doit expliquer publiquement pourquoi cet agent existe, sans reveler de raisonnement interne cache;
- retourne uniquement un JSON valide, sans markdown.

Consigne utilisateur:
{instruction}

Schema exact:
{{
  "group": {{
    "title": "titre court du groupe",
    "summary": "synthese de l'objectif collectif"
  }},
  "agents": [
    {{
      "name": "nom court",
      "role": "role clair",
      "mission": "mission concrete",
      "tools": ["capacite 1", "capacite 2"],
      "success_criteria": ["critere 1", "critere 2"],
      "system_prompt": "prompt systeme complet en francais",
      "creation_reasoning": "trace explicative publique du choix de cet agent"
    }}
  ]
}}
"""
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=3200,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    payload = extract_json_object(text_from_claude_response(response))
    raw_group = payload.get("group") or {}
    raw_agents = payload.get("agents")
    if not isinstance(raw_agents, list) or len(raw_agents) != count:
        raise ValueError("Le fournisseur IA doit retourner exactement le nombre d'agents demande.")
    group = {
        "id": group_id,
        "title": str(raw_group.get("title") or "Groupe d'agents").strip(),
        "summary": str(raw_group.get("summary") or "Equipe d'agents creee depuis le brief utilisateur.").strip(),
        "source_instruction": instruction,
        "model": ANTHROPIC_MODEL,
        "created_at": now_iso(),
    }
    agents = [normalize_agent(raw, index, instruction, group_id) for index, raw in enumerate(raw_agents)]
    return group, agents


@app.get("/health")
def health() -> dict[str, Any]:
    init_db()
    with connect_db() as db:
        group_count = db.execute("SELECT COUNT(*) AS total FROM groups").fetchone()["total"]
        agent_count = db.execute("SELECT COUNT(*) AS total FROM agents").fetchone()["total"]
        message_count = db.execute("SELECT COUNT(*) AS total FROM messages").fetchone()["total"]
    return {
        "ok": True,
        "service": APP_NAME,
        "model": ANTHROPIC_MODEL,
        "anthropic_configured": bool(ANTHROPIC_API_KEY),
        "database": "sqlite",
        "group_count": group_count,
        "agent_count": agent_count,
        "message_count": message_count,
        "api_access_protected": bool(AG_CREATOR_ACCESS_TOKEN),
    }


@app.get("/api/groups")
def list_groups(request: Request) -> dict[str, Any]:
    require_api_access(request)
    with connect_db() as db:
        groups = db.execute("SELECT * FROM groups ORDER BY created_at DESC").fetchall()
        payload = []
        for group in groups:
            agent_rows = db.execute(
                "SELECT * FROM agents WHERE group_id = ? ORDER BY created_at ASC",
                (group["id"],),
            ).fetchall()
            payload.append(group_from_row(group, [agent_from_row(row) for row in agent_rows]))
        return {"groups": payload}


@app.get("/api/groups/{group_id}")
def get_group(group_id: str, request: Request) -> dict[str, Any]:
    require_api_access(request)
    with connect_db() as db:
        group = db.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
        if not group:
            raise HTTPException(status_code=404, detail="Groupe introuvable.")
        agent_rows = db.execute(
            "SELECT * FROM agents WHERE group_id = ? ORDER BY created_at ASC",
            (group_id,),
        ).fetchall()
        return {"group": group_from_row(group, [agent_from_row(row) for row in agent_rows])}


@app.get("/api/agents")
def list_agents(request: Request) -> dict[str, Any]:
    require_api_access(request)
    with connect_db() as db:
        rows = db.execute("SELECT * FROM agents ORDER BY created_at DESC").fetchall()
        return {"agents": [agent_from_row(row) for row in rows]}


@app.get("/api/agents/{agent_id}")
def get_agent(agent_id: str, request: Request) -> dict[str, Any]:
    require_api_access(request)
    with connect_db() as db:
        row = db.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Agent introuvable.")
        return {"agent": agent_from_row(row, messages_for_agent(db, agent_id))}


@app.post("/api/agents/generate")
def generate_agents(payload: GenerateAgentsRequest, request: Request) -> dict[str, Any]:
    require_api_access(request)
    try:
        group, created = call_claude_for_group(payload.instruction, payload.count)
        insert_group_with_agents(group, created)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Generation impossible: {exc}") from exc

    return {"group": {**group, "agents": created}, "agents": created, "model": ANTHROPIC_MODEL}


@app.delete("/api/groups/{group_id}")
def delete_group(group_id: str, request: Request) -> dict[str, Any]:
    require_api_access(request)
    with connect_db() as db:
        group = db.execute("SELECT id FROM groups WHERE id = ?", (group_id,)).fetchone()
        if not group:
            raise HTTPException(status_code=404, detail="Groupe introuvable.")
        db.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        db.commit()
    return {"deleted": True, "group_id": group_id}


@app.delete("/api/agents/{agent_id}")
def delete_agent(agent_id: str, request: Request) -> dict[str, Any]:
    require_api_access(request)
    with connect_db() as db:
        row = db.execute("SELECT id, group_id FROM agents WHERE id = ?", (agent_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Agent introuvable.")
        db.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        db.commit()
    return {"deleted": True, "agent_id": agent_id, "group_id": row["group_id"]}


@app.post("/api/agents/{agent_id}/chat")
def chat_with_agent(agent_id: str, payload: ChatRequest, request: Request) -> dict[str, Any]:
    require_api_access(request)
    client = require_claude()
    with connect_db() as db:
        row = db.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Agent introuvable.")
        agent = agent_from_row(row, messages_for_agent(db, agent_id))

        user_message_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO messages (id, agent_id, role, content, visible_reasoning, model, created_at)
            VALUES (?, ?, 'user', ?, '', ?, ?)
            """,
            (user_message_id, agent_id, payload.message, ANTHROPIC_MODEL, now_iso()),
        )
        db.commit()

        history = messages_for_agent(db, agent_id)[-12:]
        shared_context = group_conversation_context(db, agent["group_id"], agent_id)

    prompt = """
Reponds uniquement en JSON valide, sans markdown:
{
  "answer": "reponse finale en francais",
  "visible_reasoning": "trace explicative courte: donne les criteres, hypotheses et etapes visibles utilisees, sans reveler de chaine de pensee interne cachee"
}
"""
    system_prompt = f"""
{agent['system_prompt']}

Memoire partagee du groupe:
{shared_context}

Tu fais partie d'un groupe d'agents. Utilise la memoire partagee ci-dessus pour rester coherent avec les
echanges des autres agents du meme groupe. Tu peux mentionner explicitement quand tu t'appuies sur une
information dite par un autre agent. Ne pretend pas avoir vu des messages absents du contexte fourni.

{prompt}
"""
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1600,
        temperature=0.3,
        system=system_prompt,
        messages=[{"role": item["role"], "content": item["content"]} for item in history],
    )
    payload = extract_json_object(text_from_claude_response(response))
    answer = str(payload.get("answer") or "").strip()
    visible_reasoning = str(payload.get("visible_reasoning") or "").strip()
    if not answer:
        raise HTTPException(status_code=502, detail="Le fournisseur IA n'a pas retourne de reponse exploitable.")

    assistant_message = {
        "id": str(uuid.uuid4()),
        "role": "assistant",
        "content": answer,
        "visible_reasoning": visible_reasoning,
        "model": ANTHROPIC_MODEL,
        "created_at": now_iso(),
    }
    with connect_db() as db:
        db.execute(
            """
            INSERT INTO messages (id, agent_id, role, content, visible_reasoning, model, created_at)
            VALUES (?, ?, 'assistant', ?, ?, ?, ?)
            """,
            (
                assistant_message["id"],
                agent_id,
                assistant_message["content"],
                assistant_message["visible_reasoning"],
                ANTHROPIC_MODEL,
                assistant_message["created_at"],
            ),
        )
        db.commit()
        fresh_agent = agent_from_row(
            db.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone(),
            messages_for_agent(db, agent_id),
        )

    return {"agent": fresh_agent, "message": assistant_message, "model": ANTHROPIC_MODEL}
