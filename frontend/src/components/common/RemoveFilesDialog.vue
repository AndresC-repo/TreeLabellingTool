<template>
  <teleport to="body">
    <div v-if="pending" class="rm-overlay" @click.self="emit('cancel')">
      <div class="rm-box">
        <h3>
          <template v-if="pending.folder">Delete folder 📁 {{ pending.folder }} ({{ n }} file{{ n === 1 ? '' : 's' }})?</template>
          <template v-else>Delete {{ n === 1 ? pending.entries[0].filename : `${n} files` }}?</template>
        </h3>
        <p class="rm-text">
          {{ n === 1 ? 'This file has' : 'Together they have' }}
          <strong>{{ pending.patchCount }}</strong> {{ pending.patchCount === 1 ? 'patch' : 'patches' }} on the server.
          Deleting removes the files, their patches and any saved outputs you haven't downloaded.
          Files already saved to <code>data/labels</code> are kept.
        </p>
        <ul v-if="n > 1" class="rm-list">
          <li v-for="e in pending.entries" :key="e.sessionId">
            {{ pathInFolder(e) }}<span v-if="pending.counts[e.sessionId]" class="rm-count"> · {{ pending.counts[e.sessionId] }} patch{{ pending.counts[e.sessionId] === 1 ? '' : 'es' }}</span>
          </li>
        </ul>
        <div class="rm-actions">
          <button @click="emit('cancel')">Cancel</button>
          <button class="danger" @click="emit('confirm')">Delete</button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { computed } from 'vue'
import { pathInFolder } from '../../utils/uploadCheck.js'
const props = defineProps({ pending: { type: Object, default: null } })
const emit = defineEmits(['cancel', 'confirm'])
const n = computed(() => props.pending?.entries.length ?? 0)
</script>

<style scoped>
.rm-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.65); display: flex; align-items: center; justify-content: center; z-index: 200; }
.rm-box { background: #12122a; border: 1px solid #335; border-radius: 10px; padding: 24px 28px; min-width: 360px; max-width: 460px; display: flex; flex-direction: column; gap: 14px; }
.rm-box h3 { margin: 0; color: #adf; font-size: 1.1rem; overflow-wrap: anywhere; }
.rm-text { margin: 0; font-size: 13px; line-height: 1.5; color: #aab; }
.rm-text strong { color: #fff; }
.rm-text code { color: #7af; }
.rm-list { margin: 0; padding: 8px 12px 8px 28px; max-height: 180px; overflow-y: auto; background: #0d0d1f; border: 1px solid #2a2a44; border-radius: 6px; font-size: 12px; color: #aac; line-height: 1.6; }
.rm-count { color: #fb4; }
.rm-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 4px; }
.rm-actions button { background: #2a2a4e; color: #cce; border: 1px solid #446; border-radius: 6px; padding: 6px 14px; font-size: 13px; cursor: pointer; }
.rm-actions button:hover { background: #3a3a6e; }
.rm-actions .danger { background: #5a2a2e; border-color: #a44; color: #fcc; }
.rm-actions .danger:hover { background: #7a3035; }
</style>
