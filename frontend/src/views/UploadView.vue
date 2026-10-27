<template>
  <div class="upload-page">
    <div class="header">
      <h1>Point Cloud Labeling Tool</h1>
      <p class="subtitle">Upload a <code>.las</code> or <code>.laz</code> file to begin labeling</p>
      <router-link to="/dataset" class="dataset-link">📊 Dataset overview — what's labelled so far</router-link>
    </div>
    <DropZone />

    <div v-if="session.sessions.length" class="recent">
      <h3>Continue with a loaded file</h3>
      <button
        v-for="s in session.sessions"
        :key="s.sessionId"
        class="recent-item"
        @click="open(s)"
        :title="s.filename"
      >
        <span class="recent-name">{{ s.filename }}</span>
        <span class="recent-pts">{{ s.pointCount?.toLocaleString() }} pts</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import DropZone from '../components/upload/DropZone.vue'
import { useSessionStore } from '../stores/session.js'
import { useToastStore } from '../stores/toast.js'

const session = useSessionStore()
const toast = useToastStore()
const router = useRouter()

onMounted(async () => {
  const dropped = await session.init()
  if (dropped) toast.warning(`${dropped} file${dropped === 1 ? ' was' : 's were'} no longer on the server and ${dropped === 1 ? 'was' : 'were'} removed from the list.`)
})

function open(entry) {
  session.switchTo(entry)
  router.push(`/session/${entry.sessionId}/view`)
}
</script>

<style scoped>
.upload-page {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  gap: 40px;
  padding: 24px;
}
.header { text-align: center; }
h1 { font-size: 2.2rem; color: #adf; font-weight: 600; margin-bottom: 8px; }
.subtitle { color: #889; font-size: 1rem; }
code { color: #7af; }
.dataset-link { display: inline-block; margin-top: 14px; color: #9c9; font-size: 14px; text-decoration: none; }
.dataset-link:hover { text-decoration: underline; }
.recent { width: 100%; max-width: 480px; display: flex; flex-direction: column; gap: 6px; }
.recent h3 { color: #889; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; }
.recent-item {
  display: flex; align-items: center; gap: 12px;
  background: #2a2a4e; color: #cce; border: 1px solid #445;
  border-radius: 8px; padding: 8px 12px; cursor: pointer; font-size: 13px; text-align: left;
}
.recent-item:hover { background: #3a3a6e; }
.recent-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.recent-pts { color: #778; flex-shrink: 0; }
</style>
