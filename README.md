# AG Creator by Altay

Application web full-stack pour creer, stocker et utiliser des groupes d'agents IA a partir d'une consigne en francais.

## Pitch entretien

AG Creator by Altay transforme une demande humaine en groupe d'agents specialises.  
Exemple:

```text
Cree 5 agents IA pour traiter les reclamations d'une assurance sante:
qualification, analyse pieces jointes, synthese client, risque juridique et controle qualite.
```

Le backend envoie cette consigne a Claude Sonnet 4.6, demande un JSON strict, sauvegarde un groupe + ses agents dans SQLite, puis permet de discuter avec chaque agent. Les conversations sont elles aussi conservees en base.

## Stack technique

- Frontend: Vue 3 + Vite
- Backend: Python + FastAPI
- IA: Anthropic Claude via l'API Messages
- Modele par defaut: `claude-sonnet-4-6`
- Base locale: SQLite
- Lancement: Docker Compose ou commandes locales Mac

## Fonctionnalites

- Creation de groupes d'agents depuis une zone de texte en francais
- Nombre d'agents configurable de 1 a 8
- Stockage SQLite des groupes crees
- Stockage SQLite des agents crees
- Stockage SQLite des messages de conversation
- Chat avec chaque agent via Claude
- Suppression d'un agent
- Suppression d'un groupe complet avec ses agents et conversations
- Affichage du prompt systeme de chaque agent
- Affichage d'une trace explicative publique
- Interface responsive: experience mobile web, confortable sur ordinateur
- Swagger API disponible sur `/docs`

## Securite de la cle API

La cle Anthropic ne doit jamais etre dans Vue, dans GitHub, dans le navigateur ou dans le code source.

Elle reste seulement:

- dans `agent-factory/.env` en local;
- ou dans les variables d'environnement du serveur en production;
- ou dans les secrets GitHub Actions si un jour tu ajoutes un pipeline CI/CD.

Le frontend appelle ton backend local. Le backend appelle Anthropic.
La cle ne traverse donc jamais le navigateur.

Important: ne commit jamais `.env`. Le fichier `.gitignore` l'exclut deja.

Mesures ajoutees dans cette demo:

- CORS limite a `FRONTEND_ORIGIN`
- methodes HTTP limitees a `GET`, `POST`, `DELETE`, `OPTIONS`
- headers de securite: `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`
- cache des reponses API desactive avec `Cache-Control: no-store`
- hotlink direct de la base evite: SQLite reste dans `backend/data`, ignore par Git
- suppression en cascade: supprimer un groupe supprime ses agents; supprimer un agent supprime ses messages
- aucune cle API dans le bundle Vue

## A propos du "raisonnement visible"

L'application affiche une trace explicative publique:

- pourquoi un agent a ete cree;
- quels criteres visibles il utilise pour repondre;
- quelles hypotheses il annonce a l'utilisateur.

Ce n'est pas la chaine de pensee interne cachee du modele. C'est volontaire: on donne de la transparence utile sans exposer de raisonnement interne sensible.

## Installation locale sur Mac

Depuis la racine du projet:

```bash
cd "/Users/altaycevik/Desktop/app-ehosp copie 2/agent-factory"
cp .env.example .env
```

Ouvre `.env` et ajoute ta cle:

```bash
ANTHROPIC_API_KEY=ta_cle_anthropic
ANTHROPIC_MODEL=claude-sonnet-4-6
FRONTEND_ORIGIN=http://localhost:5173
DATABASE_URL=sqlite:///./data/ag_creator.sqlite3
```

Ne colle jamais la cle dans le frontend.

## Lancer avec Docker

```bash
cd "/Users/altaycevik/Desktop/app-ehosp copie 2/agent-factory"
docker compose --env-file .env up --build
```

Puis ouvre:

- Frontend: http://localhost:5173
- Backend: http://localhost:8000/health
- Documentation API: http://localhost:8000/docs

Arreter:

```bash
docker compose down
```

## Lancer sans Docker

Terminal 1, backend:

```bash
cd "/Users/altaycevik/Desktop/app-ehosp copie 2/agent-factory/backend"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Terminal 2, frontend:

```bash
cd "/Users/altaycevik/Desktop/app-ehosp copie 2/agent-factory/frontend"
npm install
npm run dev
```

Puis ouvre:

```text
http://localhost:5173
```

## Routes API

### `GET /health`

Retourne l'etat du service, le modele configure, la presence de la cle Anthropic, le nombre de groupes, d'agents et de messages.

### `GET /api/groups`

Liste les groupes stockes dans SQLite, avec leurs agents.

### `GET /api/groups/{group_id}`

Retourne un groupe precis avec ses agents.

### `POST /api/agents/generate`

Cree un groupe d'agents.

```json
{
  "instruction": "Cree 4 agents pour analyser un besoin client SaaS.",
  "count": 4
}
```

### `GET /api/agents`

Liste les agents stockes dans SQLite.

### `GET /api/agents/{agent_id}`

Retourne un agent avec son historique de messages.

### `POST /api/agents/{agent_id}/chat`

Envoie un message a un agent et sauvegarde la conversation.

```json
{
  "message": "Propose un plan d'action en 5 etapes."
}
```

### `DELETE /api/agents/{agent_id}`

Supprime un agent et ses conversations.

### `DELETE /api/groups/{group_id}`

Supprime un groupe, tous ses agents et toutes les conversations rattachees.

## Architecture

```text
Vue 3 UI
  |
  | HTTP JSON
  v
FastAPI backend
  |              |
  | SQLite       | Anthropic Messages API
  v              v
groups/agents/messages  Claude Sonnet 4.6
```

## Comment expliquer le code

1. `frontend/src/App.vue` gere l'interface: brief francais, liste des agents, detail agent, chat.
2. `backend/app/main.py` expose l'API FastAPI et contient la logique d'orchestration.
3. `call_claude_for_group()` demande a Claude de produire un JSON strict: groupe + agents.
4. `insert_group_with_agents()` sauvegarde le groupe et ses agents dans SQLite.
5. `chat_with_agent()` recharge l'agent, envoie son prompt systeme a Claude, puis sauvegarde user + assistant.
6. `require_claude()` bloque les appels IA si la cle API n'est pas configuree.
7. `DATABASE_URL` permet de choisir l'emplacement SQLite sans modifier le code.

## Creer le repository GitHub proprement

Ne mets jamais un token GitHub dans un fichier, dans un commit ou dans le README.

Option recommandee avec GitHub CLI:

```bash
cd "/Users/altaycevik/Desktop/app-ehosp copie 2/agent-factory"
git init
git add .
git commit -m "Initial AG Creator by Altay"
gh auth login
gh repo create ag-creator-by-altay --private --source=. --remote=origin --push
```

Si tu veux le rendre public pour l'entretien:

```bash
gh repo edit ag-creator-by-altay --visibility public
```

## Points forts a dire au recruteur

- La cle IA est isolee cote backend.
- La sortie Claude est contrainte en JSON pour obtenir des agents exploitables.
- SQLite rend la demo persistante sans infrastructure lourde.
- L'app separe bien frontend, API, modele IA et stockage.
- Le chat reutilise le prompt systeme de l'agent selectionne.
- Les traces visibles donnent de l'explicabilite sans exposer de chaine de pensee interne.
- Docker rend l'installation reproductible.
