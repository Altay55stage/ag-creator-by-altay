# AG Creator by Altay

AG Creator by Altay est une application web full-stack qui permet de créer des groupes d'agents IA à partir d'une consigne en français, de les stocker dans SQLite, puis de discuter avec chaque agent tout en partageant le contexte entre les agents du même groupe.

Le projet reste simple à lancer en local, mais il est structuré comme une vraie application:

- frontend Vue 3 + Vite;
- backend Python FastAPI;
- persistance SQLite;
- API Anthropic Messages;
- Docker Compose;
- code d'accès API local;
- clé fournisseur IA uniquement côté backend;
- mémoire conversationnelle partagée au niveau du groupe.

## Fonctionnement

1. L'utilisateur écrit un brief en français.
2. Le backend demande au fournisseur IA de retourner un JSON strict contenant un groupe et plusieurs agents spécialisés.
3. Le backend stocke le groupe et ses agents dans SQLite.
4. L'utilisateur sélectionne un groupe, puis un agent.
5. L'utilisateur discute avec l'agent sélectionné.
6. Quand un agent répond, le backend lui fournit:
   - son prompt système;
   - son historique récent direct;
   - les messages récents des autres agents du même groupe.
7. La réponse et la trace explicative visible sont stockées dans SQLite.

Les agents d'un même groupe ne sont donc pas isolés: ils reçoivent une mémoire partagée construite côté backend à partir des conversations du groupe.

## Structure Du Projet

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

## Installation Avec Docker

Copier le modèle d'environnement:

```bash
cp .env.example .env
```

Générer un code d'accès local pour protéger l'API:

```bash
openssl rand -hex 32
```

Modifier `.env`:

```bash
# Valeur acceptee: une cle sk-ant-... ou un lien Vaultwarden/Bitwarden Send
ANTHROPIC_API_KEY=votre_cle_anthropic_ou_lien_send
ANTHROPIC_MODEL=claude-sonnet-4-6
FRONTEND_ORIGIN=http://localhost:5173
DATABASE_URL=sqlite:///./data/ag_creator.sqlite3
AG_CREATOR_ACCESS_TOKEN=votre_token_aleatoire_64_hex
```

Lancer l'application:

```bash
docker compose --env-file .env up --build
```

Ouvrir:

- frontend: http://localhost:5173
- santé backend: http://localhost:8000/health
- documentation API: http://localhost:8000/docs

Dans l'interface, coller la même valeur que `AG_CREATOR_ACCESS_TOKEN` dans le champ `Code d'acces API`.

Arrêter l'application:

```bash
docker compose down
```

## Installation Sans Docker

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

Ouvrir:

```text
http://localhost:5173
```

## Variables D'environnement

| Variable | Obligatoire | Utilisée Par | Description |
| --- | --- | --- | --- |
| `ANTHROPIC_API_KEY` | Oui | Backend | Clé secrète du fournisseur IA, ou lien Vaultwarden/Bitwarden Send contenant cette clé. Ne jamais la mettre dans le frontend. |
| `ANTHROPIC_MODEL` | Oui | Backend | Nom du modèle utilisé pour créer les agents et discuter. |
| `FRONTEND_ORIGIN` | Oui | Backend | Origine navigateur autorisée par CORS. |
| `DATABASE_URL` | Oui | Backend | Emplacement SQLite, par exemple `sqlite:///./data/ag_creator.sqlite3`. |
| `AG_CREATOR_ACCESS_TOKEN` | Oui | Backend + session utilisateur | Code d'accès local envoyé dans le header `X-AG-Creator-Token`. |

Le fichier `.env` est ignoré par Git. Il ne faut jamais committer de vrais secrets.

## Sécurité

### Clé Du Fournisseur IA

La clé fournisseur est lue uniquement par le backend. Deux formats sont acceptés:

- une clé directe `sk-ant-...`;
- un lien Vaultwarden/Bitwarden Send dont le texte contient la clé.

Le frontend Vue ne reçoit jamais cette clé. Il appelle uniquement l'API FastAPI locale.

Au démarrage, le backend résout la variable:

```python
RAW_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_API_KEY = resolve_anthropic_api_key(RAW_ANTHROPIC_API_KEY)
anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
```

Si la valeur est un lien Send de type `https://.../#/send/<id>/<key>`, le backend:

1. extrait l'URL du serveur, l'identifiant du Send et la clé du fragment;
2. appelle l'endpoint serveur `/api/sends/access/<id>` avec le header `Send-Id`;
3. récupère le texte chiffré;
4. dérive les clés de chiffrement avec HKDF SHA-256;
5. vérifie le HMAC du message;
6. déchiffre le contenu AES-CBC;
7. extrait uniquement la clé `sk-ant-...` pour initialiser le client IA.

Le lien Send n'est pas envoyé au frontend et la vraie clé n'est pas affichée dans `/health`. La route de santé expose seulement `anthropic_key_source` et `anthropic_key_resolved`.

Limites importantes:

- le Send doit contenir un texte, pas un fichier;
- le Send ne doit pas être expiré;
- si le Send est supprimé ou désactivé, le backend ne pourra plus redémarrer avec ce lien;
- en production, il vaut mieux utiliser un gestionnaire de secrets managé ou injecter directement le secret au runtime.

### Code D'accès API

Les routes applicatives sont protégées par un code d'accès local:

```http
X-AG-Creator-Token: <AG_CREATOR_ACCESS_TOKEN>
```

Le backend valide ce code avec `hmac.compare_digest`, ce qui évite une comparaison naïve de chaînes:

```python
if not hmac.compare_digest(provided, AG_CREATOR_ACCESS_TOKEN):
    raise HTTPException(status_code=401, detail="Code d'acces API invalide ou manquant.")
```

Le code est saisi manuellement dans l'interface et stocké dans `sessionStorage`. Il n'est pas présent dans le code source, ni dans Git.

### CORS

CORS est limité à `FRONTEND_ORIGIN`:

```python
allow_origins=[FRONTEND_ORIGIN]
allow_methods=["GET", "POST", "DELETE", "OPTIONS"]
allow_headers=["Content-Type", "X-AG-Creator-Token"]
```

### Headers De Sécurité

Chaque réponse reçoit les headers suivants:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- `Cache-Control: no-store`

### Sécurité Docker

Les conteneurs backend et frontend tournent avec des utilisateurs non-root.

Docker Compose refuse de démarrer si ces variables ne sont pas définies:

```yaml
ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY in .env}
AG_CREATOR_ACCESS_TOKEN: ${AG_CREATOR_ACCESS_TOKEN:?Set AG_CREATOR_ACCESS_TOKEN in .env}
```

Les données SQLite sont stockées dans un volume Docker:

```yaml
volumes:
  - ag_creator_data:/app/data
```

## Schéma SQLite

SQLite est initialisé automatiquement au démarrage du backend.

### `groups`

Stocke un groupe généré:

- `id`
- `title`
- `summary`
- `source_instruction`
- `model`
- `created_at`

### `agents`

Stocke les agents rattachés à un groupe:

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

`group_id` utilise `ON DELETE CASCADE`: supprimer un groupe supprime ses agents.

### `messages`

Stocke les conversations par agent:

- `id`
- `agent_id`
- `role`
- `content`
- `visible_reasoning`
- `model`
- `created_at`

`agent_id` utilise `ON DELETE CASCADE`: supprimer un agent supprime ses messages.

## Création Des Groupes D'agents

L'endpoint `POST /api/agents/generate` reçoit:

```json
{
  "instruction": "Cree 4 agents pour analyser un besoin client SaaS.",
  "count": 4
}
```

Le backend construit un prompt demandant une sortie JSON stricte:

```json
{
  "group": {
    "title": "titre court du groupe",
    "summary": "objectif du groupe"
  },
  "agents": [
    {
      "name": "nom de l'agent",
      "role": "role clair",
      "mission": "mission concrete",
      "tools": ["capacite"],
      "success_criteria": ["critere"],
      "system_prompt": "prompt systeme utilisable",
      "creation_reasoning": "explication publique"
    }
  ]
}
```

Le backend parse le JSON, normalise les champs, génère les UUID, puis insère le groupe et ses agents dans SQLite.

## Mémoire Partagée Entre Agents

Chaque conversation directe appartient toujours à un agent sélectionné. En revanche, avant d'appeler le fournisseur IA, le backend construit une mémoire partagée avec les messages récents de tous les agents du même groupe:

```python
shared_context = group_conversation_context(db, agent["group_id"], agent_id)
```

Cette fonction joint les tables `messages` et `agents`, filtre par `agents.group_id`, puis retourne les derniers messages du groupe sous une forme lisible:

```text
- [time] autre agent: Risk Analyst / Risk Analyst: ...
- [time] agent actif / Utilisateur: ...
- [time] autre agent: QA Agent / QA Agent: ...
```

L'agent sélectionné reçoit ensuite cette mémoire dans son contexte système:

```text
Memoire partagee du groupe:
...

Tu fais partie d'un groupe d'agents. Utilise la memoire partagee ci-dessus pour rester coherent avec les
echanges des autres agents du meme groupe.
```

C'est ce mécanisme qui permet aux agents d'un même groupe d'être au courant des échanges des autres agents. Le frontend ne reconstruit pas cette mémoire; elle est produite côté backend pour garder un comportement cohérent et contrôlé.

## Trace Explicative Visible

L'application stocke un champ `visible_reasoning` pour les messages assistant. Il s'agit d'une courte explication publique: critères utilisés, hypothèses visibles, étapes utiles.

Ce n'est pas une chaîne de pensée interne cachée. L'application demande une explication utile sans exposer de raisonnement interne sensible.

## Routes API

### `GET /health`

Route publique de santé. Retourne le modèle, le type de base de données, les compteurs et l'état de protection par code d'accès.

### `GET /api/groups`

Protégée. Liste les groupes et leurs agents.

### `GET /api/groups/{group_id}`

Protégée. Lit un groupe et ses agents.

### `POST /api/agents/generate`

Protégée. Crée un groupe et ses agents.

### `GET /api/agents`

Protégée. Liste tous les agents.

### `GET /api/agents/{agent_id}`

Protégée. Lit un agent et son historique de messages.

### `POST /api/agents/{agent_id}/chat`

Protégée. Discute avec un agent en injectant la mémoire partagée du groupe.

### `DELETE /api/agents/{agent_id}`

Protégée. Supprime un agent et ses messages.

### `DELETE /api/groups/{group_id}`

Protégée. Supprime un groupe, ses agents et leurs messages.

## Flux Frontend

`frontend/src/App.vue` gère le parcours principal:

1. stocker le code d'accès API local dans `sessionStorage`;
2. appeler `/api/groups` pour charger les groupes;
3. appeler `/api/agents/generate` pour créer un groupe;
4. sélectionner un groupe puis un agent;
5. appeler `/api/agents/{agent_id}` pour charger l'historique;
6. appeler `/api/agents/{agent_id}/chat` pour continuer une conversation;
7. appeler les routes `DELETE` pour supprimer un agent ou un groupe.

`frontend/src/styles.css` contient le système visuel responsive. L'interface est pensée mobile-first, puis s'étend en espace de travail à deux colonnes sur ordinateur.

## Flux Backend

`backend/app/main.py` contient l'API et l'orchestration:

- `init_db()` crée et migre les tables SQLite.
- `require_api_access()` protège les routes applicatives.
- `require_claude()` bloque les appels IA si la clé fournisseur est absente.
- `call_claude_for_group()` crée les définitions du groupe et des agents.
- `insert_group_with_agents()` persiste les données générées.
- `group_conversation_context()` construit la mémoire partagée entre agents du même groupe.
- `chat_with_agent()` stocke le message utilisateur, injecte la mémoire partagée, appelle le fournisseur IA, puis stocke la réponse assistant.

## Vérifications De Développement

Syntaxe backend:

```bash
python3 -m py_compile backend/app/main.py
```

Build frontend:

```bash
cd frontend
npm run build
```

Configuration Docker:

```bash
docker compose config
```

Recherche de secrets:

```bash
rg -n "ghp_|gho_|sk-ant|ANTHROPIC_API_KEY=.*[A-Za-z0-9_-]{20,}|AG_CREATOR_ACCESS_TOKEN=.*[A-Za-z0-9_-]{20,}" .
```

## Notes De Production

Ce projet est conçu comme un prototype full-stack local. Pour une production réelle, il faudrait ajouter:

- authentification utilisateur complète;
- HTTPS;
- limitation de débit;
- journalisation d'audit;
- gestionnaire de secrets managé;
- PostgreSQL à la place de SQLite si plusieurs utilisateurs écrivent en même temps;
- configuration CORS et hosts adaptée au domaine de déploiement;
- stratégie de sauvegarde des données persistantes.
