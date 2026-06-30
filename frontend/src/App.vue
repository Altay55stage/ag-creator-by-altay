<script setup>
import { computed, onMounted, ref } from 'vue';

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const instruction = ref(
  "Cree 5 agents IA pour aider une equipe support a traiter les reclamations d'une assurance sante: qualification, analyse pieces jointes, synthese client, risque juridique et controle qualite."
);
const count = ref(5);
const groups = ref([]);
const selectedGroupId = ref('');
const selectedAgentId = ref('');
const chatInput = ref('');
const loading = ref(false);
const refreshing = ref(false);
const chatting = ref(false);
const deleting = ref(false);
const error = ref('');
const health = ref(null);
const accessToken = ref(sessionStorage.getItem('agCreatorAccessToken') || '');
const accessInput = ref(accessToken.value);

const selectedGroup = computed(() => groups.value.find((group) => group.id === selectedGroupId.value));
const agents = computed(() => groups.value.flatMap((group) => group.agents || []));
const selectedAgent = computed(() => agents.value.find((agent) => agent.id === selectedAgentId.value));
const totalMessages = computed(() => health.value?.message_count || 0);

async function fetchJson(path, options = {}) {
  const secureHeaders = accessToken.value ? { 'X-AG-Creator-Token': accessToken.value } : {};
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: { 'Content-Type': 'application/json', ...secureHeaders, ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || payload.error || 'Erreur API');
  }
  return payload;
}

function saveAccessToken() {
  accessToken.value = accessInput.value.trim();
  if (accessToken.value) {
    sessionStorage.setItem('agCreatorAccessToken', accessToken.value);
  } else {
    sessionStorage.removeItem('agCreatorAccessToken');
  }
  error.value = '';
  loadGroups();
}

async function loadHealth() {
  try {
    health.value = await fetchJson('/health');
  } catch {
    health.value = { ok: false, anthropic_configured: false, model: 'indisponible', group_count: 0, agent_count: 0 };
  }
}

async function loadGroups() {
  refreshing.value = true;
  try {
    const payload = await fetchJson('/api/groups');
    groups.value = payload.groups;
    if (!selectedGroupId.value && groups.value.length) {
      selectedGroupId.value = groups.value[0].id;
      selectedAgentId.value = groups.value[0].agents?.[0]?.id || '';
    }
  } catch (err) {
    error.value = err.message;
  } finally {
    refreshing.value = false;
  }
}

async function hydrateAgent(agentId) {
  const payload = await fetchJson(`/api/agents/${agentId}`);
  groups.value = groups.value.map((group) => ({
    ...group,
    agents: (group.agents || []).map((agent) => (agent.id === agentId ? payload.agent : agent)),
  }));
}

async function selectGroup(groupId) {
  selectedGroupId.value = groupId;
  const group = groups.value.find((item) => item.id === groupId);
  selectedAgentId.value = group?.agents?.[0]?.id || '';
  error.value = '';
}

async function selectAgent(agentId) {
  selectedAgentId.value = agentId;
  const group = groups.value.find((item) => item.agents?.some((agent) => agent.id === agentId));
  if (group) selectedGroupId.value = group.id;
  error.value = '';
  try {
    await hydrateAgent(agentId);
  } catch (err) {
    error.value = err.message;
  }
}

async function createGroup() {
  error.value = '';
  loading.value = true;
  try {
    const payload = await fetchJson('/api/agents/generate', {
      method: 'POST',
      body: JSON.stringify({ instruction: instruction.value, count: Number(count.value) }),
    });
    groups.value = [payload.group, ...groups.value];
    selectedGroupId.value = payload.group.id;
    selectedAgentId.value = payload.group.agents?.[0]?.id || '';
    await loadHealth();
  } catch (err) {
    error.value = err.message;
  } finally {
    loading.value = false;
  }
}

async function deleteGroup(groupId) {
  if (!window.confirm('Supprimer ce groupe et toutes ses conversations ?')) return;
  deleting.value = true;
  error.value = '';
  try {
    await fetchJson(`/api/groups/${groupId}`, { method: 'DELETE' });
    groups.value = groups.value.filter((group) => group.id !== groupId);
    if (selectedGroupId.value === groupId) {
      selectedGroupId.value = groups.value[0]?.id || '';
      selectedAgentId.value = groups.value[0]?.agents?.[0]?.id || '';
    }
    await loadHealth();
  } catch (err) {
    error.value = err.message;
  } finally {
    deleting.value = false;
  }
}

async function deleteAgent(agentId) {
  if (!window.confirm('Supprimer cet agent et ses conversations ?')) return;
  deleting.value = true;
  error.value = '';
  try {
    await fetchJson(`/api/agents/${agentId}`, { method: 'DELETE' });
    groups.value = groups.value
      .map((group) => ({ ...group, agents: (group.agents || []).filter((agent) => agent.id !== agentId) }))
      .filter((group) => group.agents.length > 0);
    if (selectedAgentId.value === agentId) {
      const activeGroup = groups.value.find((group) => group.id === selectedGroupId.value) || groups.value[0];
      selectedGroupId.value = activeGroup?.id || '';
      selectedAgentId.value = activeGroup?.agents?.[0]?.id || '';
    }
    await loadHealth();
  } catch (err) {
    error.value = err.message;
  } finally {
    deleting.value = false;
  }
}

async function sendMessage() {
  if (!selectedAgent.value || !chatInput.value.trim()) return;
  const message = chatInput.value.trim();
  chatInput.value = '';
  chatting.value = true;
  error.value = '';
  try {
    const payload = await fetchJson(`/api/agents/${selectedAgent.value.id}/chat`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    });
    groups.value = groups.value.map((group) => ({
      ...group,
      agents: (group.agents || []).map((agent) => (agent.id === payload.agent.id ? payload.agent : agent)),
    }));
    await loadHealth();
  } catch (err) {
    error.value = err.message;
  } finally {
    chatting.value = false;
  }
}

onMounted(async () => {
  await loadHealth();
  await loadGroups();
});
</script>

<template>
  <main class="app-shell">
    <section class="hero">
      <div class="brand-block">
        <span class="brand-mark">AG</span>
        <div>
          <p class="eyebrow">Multi-agent workspace</p>
          <h1>AG Creator by Altay</h1>
          <p class="subtitle">
            Transforme une consigne francaise en groupes d'agents, conserve les conversations,
            et partage la memoire entre les agents d'un meme groupe.
          </p>
        </div>
      </div>

      <div class="security-strip">
        <div class="status" :class="{ ready: health?.anthropic_configured }">
          <span></span>
          {{ health?.anthropic_configured ? 'IA connectee' : 'Configuration requise' }}
        </div>
        <div class="metric">
          <strong>{{ health?.group_count || groups.length }}</strong>
          <small>groupes</small>
        </div>
        <div class="metric">
          <strong>{{ totalMessages }}</strong>
          <small>messages</small>
        </div>
      </div>
    </section>

    <section class="workspace">
      <aside class="left-rail">
        <div class="panel compose-panel">
          <div class="panel-title">
            <p class="eyebrow">Creation</p>
            <h2>Nouveau groupe</h2>
          </div>
          <textarea v-model="instruction" aria-label="Consigne de creation du groupe d'agents" />
          <div class="controls">
            <label>
              Agents
              <input v-model="count" min="1" max="8" type="number" />
            </label>
            <button class="primary-action" :disabled="loading" @click="createGroup">
              {{ loading ? 'Creation...' : 'Creer le groupe' }}
            </button>
          </div>
          <p v-if="error" class="error">{{ error }}</p>
          <form class="access-form" @submit.prevent="saveAccessToken">
            <label>
              Code d'acces API
              <input v-model="accessInput" type="password" placeholder="Defini dans .env" />
            </label>
            <button class="ghost-action">Enregistrer</button>
          </form>
          <div class="security-note">
            <strong>Securite</strong>
            <span>La cle IA reste sur le backend. Le code d'acces protege les routes applicatives.</span>
          </div>
        </div>

        <div class="panel agents-panel">
          <div class="section-title">
            <div>
              <p class="eyebrow">SQLite</p>
              <h2>Groupes sauvegardes</h2>
            </div>
            <button class="ghost-action" :disabled="refreshing" @click="loadGroups">
              {{ refreshing ? '...' : 'Actualiser' }}
            </button>
          </div>

          <article
            v-for="group in groups"
            :key="group.id"
            class="group-card"
            :class="{ active: group.id === selectedGroupId }"
          >
            <button class="group-main" @click="selectGroup(group.id)">
              <strong>{{ group.title }}</strong>
              <span>{{ group.summary }}</span>
              <small>{{ group.agents?.length || 0 }} agent(s)</small>
            </button>
            <button class="danger-action" :disabled="deleting" @click="deleteGroup(group.id)">Supprimer</button>

            <div v-if="group.id === selectedGroupId" class="agent-stack">
              <button
                v-for="agent in group.agents"
                :key="agent.id"
                class="agent-row"
                :class="{ active: agent.id === selectedAgentId }"
                @click="selectAgent(agent.id)"
              >
                <strong>{{ agent.name }}</strong>
                <span>{{ agent.role }}</span>
              </button>
            </div>
          </article>
        </div>
      </aside>

      <section v-if="selectedAgent" class="panel agent-detail">
        <header class="agent-head">
          <div>
            <p class="eyebrow">{{ selectedGroup?.title || 'Groupe actif' }}</p>
            <h2>{{ selectedAgent.name }}</h2>
            <p class="role-line">{{ selectedAgent.role }}</p>
          </div>
          <div class="header-actions">
            <div class="model-badge">{{ selectedAgent.model || health?.model }}</div>
            <button class="danger-action" :disabled="deleting" @click="deleteAgent(selectedAgent.id)">Supprimer agent</button>
          </div>
        </header>

        <div class="mission-card">
          <p>{{ selectedAgent.mission }}</p>
        </div>

        <div class="insight-grid">
          <article>
            <h3>Capacites</h3>
            <ul>
              <li v-for="tool in selectedAgent.tools" :key="tool">{{ tool }}</li>
            </ul>
          </article>
          <article>
            <h3>Criteres de succes</h3>
            <ul>
              <li v-for="criteria in selectedAgent.success_criteria" :key="criteria">{{ criteria }}</li>
            </ul>
          </article>
          <article class="wide">
            <h3>Trace explicative de creation</h3>
            <p>{{ selectedAgent.creation_reasoning }}</p>
          </article>
        </div>

        <details class="system-prompt">
          <summary>Voir le prompt systeme</summary>
          <pre>{{ selectedAgent.system_prompt }}</pre>
        </details>

        <div class="chat-panel">
          <div class="section-title">
            <div>
              <p class="eyebrow">Conversation</p>
              <h2>Parler avec l'agent</h2>
            </div>
          </div>

          <div class="messages">
            <p v-if="!selectedAgent.messages?.length" class="empty-message">
              Aucun message pour cet agent. Pose une question pour demarrer la conversation.
            </p>
            <div
              v-for="message in selectedAgent.messages"
              :key="message.id || `${message.created_at}-${message.role}`"
              class="message"
              :class="message.role"
            >
              <strong>{{ message.role === 'user' ? 'Toi' : selectedAgent.name }}</strong>
              <span>{{ message.content }}</span>
              <details v-if="message.visible_reasoning" class="reasoning">
                <summary>Trace explicative visible</summary>
                <p>{{ message.visible_reasoning }}</p>
              </details>
            </div>
          </div>

          <form @submit.prevent="sendMessage">
            <input v-model="chatInput" placeholder="Demande une analyse, une decision, un plan..." />
            <button :disabled="chatting || !chatInput.trim()">{{ chatting ? 'Envoi...' : 'Envoyer' }}</button>
          </form>
        </div>
      </section>

      <section v-else class="panel empty-state">
        <p class="eyebrow">Pret</p>
        <h2>Cree ton premier groupe d'agents</h2>
        <p>Chaque groupe conserve ses agents et chaque agent conserve son historique de conversation.</p>
      </section>
    </section>
  </main>
</template>
