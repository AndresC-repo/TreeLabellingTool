<template>
  <div class="patch-legend">
    <h3>Classification</h3>
    <div v-if="loading" class="hint">Loading…</div>
    <div v-else-if="entries.length === 0" class="hint">No labels applied yet</div>
    <div v-for="e in entries" :key="e.value" class="legend-row" :class="{ busy: busy === e.value }">
      <button v-if="e.value !== 0" class="unlabel" :disabled="busy !== null"
              :title="`Remove label ${e.value} from these ${e.count.toLocaleString()} points (set them to 0) — Ctrl+Z undoes`"
              @click="relabel(e.value, 0)">✕</button>
      <span v-else class="unlabel-space"></span>
      <span class="swatch" :style="{ background: e.color }"></span>
      <input v-if="editing === e.value" ref="editInput" class="relabel-input" type="number" min="0" step="1"
             v-model="editValue" @keydown.enter.prevent="commitEdit(e.value)" @keydown.esc.stop="editing = null"
             @blur="commitEdit(e.value)" />
      <span v-else class="lbl" title="Double-click to give these points another label"
            @dblclick="startEdit(e.value)">{{ labelName(e.value) }}</span>
      <span class="cnt">{{ e.count.toLocaleString() }}</span>
    </div>
    <p v-if="entries.length" class="hint tip">✕ removes a label · double-click a label to change it</p>

  </div>
</template>

<script setup>
import { ref, watch, onMounted, nextTick } from 'vue'
import { getPatchColormap, relabelAll } from '../../api/client.js'
import { useView2DStore } from '../../stores/view2d.js'
import { useToastStore } from '../../stores/toast.js'
import { usePatch3DStore } from '../../stores/patch3d.js'
import { useRoute } from 'vue-router'

const route = useRoute()
const store = usePatch3DStore()
const entries = ref([])
const loading = ref(false)
const view2d = useView2DStore()
const toast = useToastStore()
const busy = ref(null)          // label value being changed
const editing = ref(null)       // label value whose name is being edited
const editValue = ref('')
const editInput = ref(null)

async function relabel(from, to) {
  if (from === to || busy.value !== null) return
  busy.value = from
  try {
    const res = await relabelAll(route.params.id, route.params.patchId, from, to)
    const { applied, applied_indices } = res.data
    if (applied > 0) {
      store.lastApplied = { indices: applied_indices, labelValue: to, protectClasses: false }
      if (to !== 0) store.addAppliedLabel(to)
      view2d.markLabelled(route.params.patchId)
    }
  } catch (err) {
    toast.error('Relabel failed: ' + (err.response?.data?.detail || err.message))
  } finally {
    busy.value = null
  }
}

async function startEdit(value) {
  editing.value = value
  editValue.value = String(value)
  await nextTick()
  const el = Array.isArray(editInput.value) ? editInput.value[0] : editInput.value
  el?.focus(); el?.select()
}
function commitEdit(from) {
  if (editing.value !== from) return
  editing.value = null
  const to = Number(editValue.value)
  if (!Number.isInteger(to) || to < 0) { if (String(editValue.value).trim()) toast.error('A label must be a whole number ≥ 0'); return }
  relabel(from, to)
}

const KNOWN_LABELS = {
  0: 'GND',
  1: 'Unclassified',
  2: 'Ground',
  3: 'Low Vegetation',
  4: 'Medium Vegetation',
  5: 'High Vegetation',
  6: 'Building',
  7: 'Low Point (Noise)',
  9: 'Water',
  17: 'Bridge Deck',
  18: 'High Noise',
}

function labelName(value) {
  const known = KNOWN_LABELS[value]
  return known ? `${value} - ${known}` : String(value)
}

async function refresh() {
  loading.value = true
  try {
    const res = await getPatchColormap(route.params.id, route.params.patchId)
    entries.value = res.data.entries
  } catch {
    entries.value = []
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

// Refresh whenever a label is applied
watch(() => store.lastApplied, (v) => { if (v) refresh() })
watch(() => store.undoResult, (v) => { if (v) refresh() })
</script>

<style scoped>
.patch-legend { color: #eee; }
h3 { color: #adf; margin-bottom: 10px; font-size: 14px; font-weight: 600; }
.legend-row {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 6px; font-size: 12px;
}
.swatch {
  width: 13px; height: 13px; border-radius: 3px;
  flex-shrink: 0; border: 1px solid rgba(255,255,255,0.15);
}
.lbl { flex: 1; color: #cce; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cnt { color: #556; font-size: 11px; white-space: nowrap; }
.hint { font-size: 12px; color: #556; }
.hint.tip { font-size: 10.5px; margin-top: 8px; }
.legend-row.busy { opacity: 0.5; }
.unlabel { width: 16px; height: 16px; padding: 0; flex-shrink: 0; background: none; border: 1px solid transparent;
  border-radius: 3px; color: #a66; font-size: 10px; line-height: 1; cursor: pointer; }
.unlabel:hover:not(:disabled) { color: #fff; background: #833; border-color: #a44; }
.unlabel:disabled { cursor: default; opacity: 0.4; }
.unlabel-space { width: 16px; flex-shrink: 0; }
.lbl { cursor: text; user-select: none; }
.relabel-input { flex: 1; min-width: 0; background: #0e1226; color: #fff; border: 1px solid #5a8adf;
  border-radius: 3px; font-size: 12px; padding: 1px 4px; }

</style>
