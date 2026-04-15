<template>
  <div class="inference-legend">
    <h3>Inference <span class="ver" v-if="versionLabel">({{ versionLabel }})</span></h3>
    <div v-if="!store.predictionLegend.length" class="hint">No inference run yet</div>
    <div v-for="e in store.predictionLegend" :key="e.label" class="legend-row">
      <span class="swatch" :style="{ background: e.color }"></span>
      <span class="lbl">{{ e.label }} — {{ e.name }}</span>
      <span class="cnt">{{ e.count.toLocaleString() }}</span>
    </div>
    <button
      v-if="store.predictionLegend.length"
      class="apply-btn"
      :disabled="applying"
      @click="applyToLabels"
      title="Write inference results into the Labels layer so they can be saved"
    >
      {{ applying ? 'Applying…' : 'Apply to Labels' }}
    </button>
    <p v-if="applied" class="ok">Applied — switch to Labels view to verify</p>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { usePatch3DStore } from '../../stores/patch3d.js'
import { applyLabelsBulk } from '../../api/client.js'

const route = useRoute()
const store = usePatch3DStore()

const VERSION_LABELS = { v1: 'XYZ', v2: 'XYZ+C', v3: 'XYZ+I', v4: 'XYZ+I+C' }
const versionLabel = computed(() => VERSION_LABELS[store.inferenceVersion] ?? '')

const applying = ref(false)
const applied  = ref(false)

async function applyToLabels() {
  if (!store.predictionLegend.length) return
  applying.value = true
  applied.value  = false
  try {
    // Rebuild flat labels array from the legend (we stored it in store.inferenceLabels)
    await applyLabelsBulk(
      route.params.id,
      route.params.patchId,
      store.inferenceLabels,
    )
    // Add unique non-zero labels to the applied-labels list so LabelPanel knows them
    for (const e of store.predictionLegend) {
      if (e.label !== 0) store.addAppliedLabel(e.label)
    }
    applied.value = true
  } catch (err) {
    console.error('Apply to labels failed:', err)
  } finally {
    applying.value = false
  }
}
</script>

<style scoped>
.inference-legend { color: #eee; }
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
.ver { font-size: 11px; color: #778; font-weight: normal; }
.apply-btn {
  margin-top: 10px; width: 100%; padding: 8px;
  background: #2a4a6e; border: 1px solid #4a7aae;
  border-radius: 5px; color: #adf; cursor: pointer; font-size: 12px;
}
.apply-btn:hover:not(:disabled) { background: #3a5a8e; }
.apply-btn:disabled { opacity: 0.4; cursor: default; }
.ok { margin-top: 6px; font-size: 11px; color: #6c6; }
</style>
