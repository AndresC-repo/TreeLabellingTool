<template>
  <div class="patch-legend">
    <h3>Classification</h3>
    <div v-if="loading" class="hint">Loading…</div>
    <div v-else-if="entries.length === 0" class="hint">No labels applied yet</div>
    <div v-for="e in entries" :key="e.value" class="legend-row">
      <span class="swatch" :style="{ background: e.color }"></span>
      <span class="lbl">{{ labelName(e.value) }}</span>
      <span class="cnt">{{ e.count.toLocaleString() }}</span>
    </div>

    <!-- Training example — only shown when inference has been run (semanticLabels exist) -->
    <div v-if="store.semanticLabels" class="training-section">
      <button
        class="training-btn"
        :disabled="savingTraining"
        @click="saveTrainingExample"
        title="Save the current corrected labels as a ground-truth training example for auto-tune"
      >
        {{ savingTraining ? 'Saving…' : 'Save as Training Example' }}
      </button>
      <div v-if="trainingMessage" class="training-note">{{ trainingMessage }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { getPatchColormap, markTrainingExample, restoreFromClient } from '../../api/client.js'
import { usePatch3DStore } from '../../stores/patch3d.js'
import { useRoute } from 'vue-router'
import { getPatchCache } from '../../composables/pointCloudCache.js'

const route = useRoute()
const store = usePatch3DStore()
const entries = ref([])
const loading = ref(false)
const savingTraining  = ref(false)
const trainingMessage = ref('')

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

async function tryRestorePatch() {
  const { positions, origCls } = getPatchCache()
  if (!positions || !origCls) return false
  const n = positions.length / 3
  const buf = new Float32Array(n * 4)
  for (let i = 0; i < n; i++) {
    buf[i*4]   = positions[i*3]
    buf[i*4+1] = positions[i*3+1]
    buf[i*4+2] = positions[i*3+2]
    buf[i*4+3] = origCls[i]
  }
  try {
    await restoreFromClient(route.params.id, route.params.patchId, buf.buffer)
    return true
  } catch {
    return false
  }
}

async function saveTrainingExample() {
  if (!store.semanticLabels || savingTraining.value) return
  savingTraining.value  = true
  trainingMessage.value = ''

  async function doSave() {
    const res = await markTrainingExample(
      route.params.id,
      route.params.patchId,
      Array.from(store.semanticLabels),
    )
    const { n_trees, total_examples } = res.data
    trainingMessage.value = `Saved ✓ — ${n_trees} trees, ${total_examples} example${total_examples > 1 ? 's' : ''} total`
  }

  try {
    await doSave()
  } catch (err) {
    if (err.response?.status === 404) {
      trainingMessage.value = 'Recovering patch data…'
      const recovered = await tryRestorePatch()
      if (recovered) {
        try {
          await doSave()
          return
        } catch (e2) {
          console.error('Save training example failed after recovery:', e2)
          trainingMessage.value = 'Save failed after recovery — see console'
        }
      } else {
        trainingMessage.value = 'Server lost patch file and browser cache is empty — reload page'
      }
    } else {
      console.error('Save training example failed:', err)
      trainingMessage.value = 'Save failed — see console'
    }
  } finally {
    savingTraining.value = false
  }
}
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

.training-section { margin-top: 10px; }
.training-btn {
  width: 100%; padding: 7px;
  background: #1e3828; border: 1px solid #3a7a4e;
  border-radius: 5px; color: #9c9; cursor: pointer; font-size: 12px;
}
.training-btn:hover:not(:disabled) { background: #2a4e38; }
.training-btn:disabled { opacity: 0.4; cursor: default; }
.training-note {
  margin-top: 4px; font-size: 10px; color: #8d8; text-align: center;
  background: #0a1e14; border: 1px solid #2a5a38;
  border-radius: 4px; padding: 4px 8px;
}
</style>
