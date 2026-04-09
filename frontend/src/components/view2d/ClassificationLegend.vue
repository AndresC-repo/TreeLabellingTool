<template>
  <aside class="legend-panel">
    <h3>Classification</h3>
    <div v-if="loading" class="hint">Loading…</div>
    <div v-else-if="entries.length === 0" class="hint">No data</div>
    <div v-for="e in entries" :key="e.value" class="legend-row">
      <span class="swatch" :style="{ background: e.color }"></span>
      <span class="lbl">{{ e.label }}</span>
      <span class="cnt">{{ e.count.toLocaleString() }}</span>
    </div>
  </aside>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { getColormap } from '../../api/client.js'
import { useRoute } from 'vue-router'

const route = useRoute()
const entries = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await getColormap(route.params.id, 'classification')
    entries.value = res.data.entries
  } catch (e) {
    entries.value = []
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.legend-panel {
  width: 190px;
  background: #0d0d1f;
  border-right: 1px solid #334;
  padding: 14px 12px;
  overflow-y: auto;
  flex-shrink: 0;
}
h3 {
  color: #adf; font-size: 12px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.06em;
  margin-bottom: 12px;
}
.legend-row {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 7px; font-size: 12px;
}
.swatch {
  width: 14px; height: 14px; border-radius: 3px;
  flex-shrink: 0; border: 1px solid rgba(255,255,255,0.1);
}
.lbl { flex: 1; color: #cce; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cnt { color: #556; font-size: 11px; white-space: nowrap; }
.hint { font-size: 12px; color: #556; }
</style>
