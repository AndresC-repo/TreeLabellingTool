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
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { getPatchColormap } from '../../api/client.js'
import { usePatch3DStore } from '../../stores/patch3d.js'
import { useRoute } from 'vue-router'

const route = useRoute()
const store = usePatch3DStore()
const entries = ref([])
const loading = ref(false)

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
</style>
