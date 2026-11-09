<template>
  <div class="upload-page">
    <div class="help-corner"><HelpButton page="upload" /></div>
    <div class="header">
      <h1>Point Cloud Labeling Tool</h1>
      <p class="subtitle">Upload a <code>.las</code> or <code>.laz</code> file to begin labeling</p>
      <div class="header-links">
        <router-link to="/dataset" class="dataset-link">📊 Dataset overview — what's labelled so far</router-link>
        <button class="split-link" @click="splitOpen = true"
                title="Cut a file that is too big to work with into a grid of tiles, then load them here as a folder or download them as a ZIP">
          ✂ Split a large file into tiles
        </button>
      </div>
    </div>
    <DropZone />
    <SplitDialog v-model:open="splitOpen" />
    <RemoveFilesDialog :pending="pendingRemove" @cancel="pendingRemove = null" @confirm="confirmRemove" />

    <div v-if="session.sessions.length" class="recent">
      <h3>Continue with a loaded file</h3>
      <div v-for="s in grouped.loose" :key="s.sessionId" class="recent-item" role="button" tabindex="0"
           @click="open(s)" @keydown.enter="open(s)" :title="s.filename">
        <span class="recent-name">{{ s.filename }}</span>
        <span class="recent-pts">{{ s.pointCount?.toLocaleString() }} pts</span>
        <button class="rm" :disabled="removing" @click.stop="requestRemove([s])" title="Delete this file and its patches">✕</button>
      </div>
      <details v-for="f in grouped.folders" :key="f.name" class="recent-folder">
        <summary :title="f.name">
          <span class="recent-name">📁 {{ f.name }}</span>
          <span class="recent-pts">{{ f.items.length }} file{{ f.items.length === 1 ? '' : 's' }}</span>
          <button class="rm" :disabled="removing" @click.stop.prevent="requestRemove(f.items, f.name)"
                  :title="`Delete the folder: all ${f.items.length} files and their patches`">✕</button>
        </summary>
        <div v-for="s in f.items" :key="s.sessionId" class="recent-item in-folder" role="button" tabindex="0"
             @click="open(s)" @keydown.enter="open(s)" :title="`${s.folder}/${s.filename}`">
          <span class="recent-name">{{ pathInFolder(s) }}</span>
          <span class="recent-pts">{{ s.pointCount?.toLocaleString() }} pts</span>
          <button class="rm" :disabled="removing" @click.stop="requestRemove([s])" title="Delete this file and its patches">✕</button>
        </div>
      </details>
    </div>
  </div>
</template>

<script setup>
import { onMounted, computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import DropZone from '../components/upload/DropZone.vue'
import HelpButton from '../components/common/HelpButton.vue'
import SplitDialog from '../components/common/SplitDialog.vue'
import RemoveFilesDialog from '../components/common/RemoveFilesDialog.vue'
import { useRemoveFiles } from '../composables/useRemoveFiles.js'
import { useSessionStore } from '../stores/session.js'
import { useToastStore } from '../stores/toast.js'
import { groupByFolder, pathInFolder } from '../utils/uploadCheck.js'

const session = useSessionStore()
const toast = useToastStore()
const router = useRouter()
const grouped = computed(() => groupByFolder(session.sessions))
const splitOpen = ref(false)
const { removing, pendingRemove, requestRemove, confirmRemove } = useRemoveFiles()

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
.help-corner { position: fixed; top: 14px; right: 16px; z-index: 50; }
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
.header-links { display: flex; flex-direction: column; align-items: center; gap: 8px; margin-top: 14px; }
.dataset-link { display: inline-block; color: #9c9; font-size: 14px; text-decoration: none; }
.split-link { background: none; border: none; color: #9bd; font-size: 14px; cursor: pointer; padding: 0; }
.split-link:hover { text-decoration: underline; }
.rm { margin-left: 4px; background: none; border: 1px solid transparent; color: #889; border-radius: 4px; font-size: 12px; padding: 1px 6px; cursor: pointer; opacity: 0.55; }
.recent-item:hover .rm, .recent-folder summary:hover .rm { opacity: 1; }
.rm:hover:not(:disabled) { color: #fcc; border-color: #a44; background: #3a1f24; }
.rm:disabled { cursor: default; }
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
.recent-folder summary {
  display: flex; align-items: center; gap: 12px; list-style: none;
  background: #23233f; color: #cde; border: 1px solid #445; border-radius: 8px;
  padding: 8px 12px; cursor: pointer; font-size: 13px;
}
.recent-folder summary::-webkit-details-marker { display: none; }
.recent-folder summary::before { content: '▸'; color: #889; font-size: 11px; }
.recent-folder[open] summary::before { content: '▾'; }
.recent-folder summary:hover { background: #2e2e55; }
.recent-folder .in-folder { width: calc(100% - 22px); margin: 5px 0 0 22px; }
</style>
