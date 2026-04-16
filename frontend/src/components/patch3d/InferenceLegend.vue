<template>
  <div class="inference-legend">
    <h3>Inference <span class="ver" v-if="versionLabel">({{ versionLabel }})</span></h3>
    <div v-if="!store.predictionLegend.length" class="hint">No inference run yet</div>
    <div v-for="e in store.predictionLegend" :key="e.label" class="legend-row">
      <span class="swatch" :style="{ background: e.color }"></span>
      <span class="lbl">{{ e.label }} — {{ e.name }}</span>
      <span class="cnt">{{ e.count.toLocaleString() }}</span>
    </div>

    <!-- Segment controls — only shown while label 101 (semantic tree) exists -->
    <div v-if="hasTreeLabel" class="segment-controls">
      <label class="param-label">
        Min points/tree
        <input
          v-model.number="minTreePoints"
          type="number" min="1" step="100"
          class="param-input"
          title="Instances with fewer points are merged into the nearest valid tree"
        />
      </label>
      <button
        class="segment-btn"
        :disabled="store.segmenting || applying"
        @click="runSegmentation"
        title="Cluster tree points into individual instances using CHM local maxima"
      >
        {{ store.segmenting ? 'Segmenting…' : 'Segment Tree Instances' }}
      </button>
    </div>
    <p v-if="instanceMessage" class="info-msg">{{ instanceMessage }}</p>

    <button
      v-if="store.predictionLegend.length"
      class="apply-btn"
      :disabled="applying || store.segmenting"
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
import { applyLabelsBulk, segmentTrees } from '../../api/client.js'

const emit = defineEmits(['segment-done'])

const route = useRoute()
const store = usePatch3DStore()

const VERSION_LABELS = { v1: 'XYZ', v2: 'XYZ+C', v3: 'XYZ+I', v4: 'XYZ+I+C' }
const versionLabel = computed(() => VERSION_LABELS[store.inferenceVersion] ?? '')

const applying        = ref(false)
const applied         = ref(false)
const instanceMessage = ref('')
const minTreePoints   = ref(500)

// Show segment controls as long as we have inference data.
// Stays visible after segmentation so the user can adjust min_tree_points and re-run.
const hasTreeLabel = computed(() => store.inferenceLabels !== null)

// Mirrors paletteColor() in usePointCloud3D.js / _paletteHex() in CanvasRenderer3D.vue
function _paletteHex(labelValue) {
  let r, g, b
  if (labelValue === 0) { r = 0.28; g = 0.28; b = 0.32 }
  else if (labelValue >= 101 && labelValue <= 108) {
    const P = [[1,0,1],[0,1,1],[1,1,0],[1,.5,0],[.5,0,1],[0,1,.5],[1,0,.5],[.5,1,0]]
    ;[r, g, b] = P[labelValue - 101]
  } else {
    const h = ((labelValue * 137.508) % 360) / 360
    const s = 0.85, l = 0.55
    const q = l + s - l * s, p = 2 * l - q
    const hue2 = t => {
      if (t < 0) t += 1; if (t > 1) t -= 1
      if (t < 1/6) return p + (q - p) * 6 * t
      if (t < 1/2) return q
      if (t < 2/3) return p + (q - p) * (2/3 - t) * 6
      return p
    }
    r = hue2(h + 1/3); g = hue2(h); b = hue2(h - 1/3)
  }
  const hex = v => Math.round(Math.min(Math.max(v, 0), 1) * 255).toString(16).padStart(2, '0')
  return `#${hex(r)}${hex(g)}${hex(b)}`
}

async function runSegmentation() {
  if (!store.semanticLabels || store.segmenting) return
  store.segmenting = true
  instanceMessage.value = ''
  applied.value = false
  try {
    const res = await segmentTrees(
      route.params.id,
      route.params.patchId,
      Array.from(store.semanticLabels),   // always use original 0/101 labels, not instance IDs
      { min_tree_points: minTreePoints.value },
    )
    const { labels, tree_count } = res.data

    store.inferenceLabels   = labels
    store.segmentationPeaks = res.data.peaks

    // Rebuild legend with instance entries
    const counts = {}
    for (const lbl of labels) counts[lbl] = (counts[lbl] || 0) + 1

    const instanceName = v =>
      v === 0   ? 'Non-tree' :
      (v === 201 && tree_count <= 1) ? 'Tree (ungrouped)' :
      `Tree #${v - 200}`

    store.predictionLegend = Object.entries(counts)
      .sort(([a], [b]) => Number(a) - Number(b))
      .map(([lbl, count]) => ({
        label: Number(lbl),
        name:  instanceName(Number(lbl)),
        color: _paletteHex(Number(lbl)),
        count,
      }))

    instanceMessage.value =
      tree_count === 0 ? 'No tree instances found' :
      tree_count === 1 ? '1 tree instance found' :
      `${tree_count} tree instances found`

    emit('segment-done', labels)
  } catch (err) {
    console.error('Segmentation failed:', err)
    instanceMessage.value = 'Segmentation failed — see console'
  } finally {
    store.segmenting = false
  }
}

async function applyToLabels() {
  if (!store.predictionLegend.length) return
  applying.value = true
  applied.value  = false
  try {
    await applyLabelsBulk(
      route.params.id,
      route.params.patchId,
      store.inferenceLabels,
    )
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
.segment-controls { margin-top: 10px; display: flex; flex-direction: column; gap: 6px; }
.param-label {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 11px; color: #88a;
}
.param-input {
  width: 72px; background: #1e2840; color: #eee;
  border: 1px solid #445; border-radius: 4px;
  padding: 3px 6px; font-size: 11px; text-align: right;
}
.segment-btn {
  width: 100%; padding: 8px;
  background: #1a4a2e; border: 1px solid #3a8a4e;
  border-radius: 5px; color: #afd; cursor: pointer; font-size: 12px;
}
.segment-btn:hover:not(:disabled) { background: #2a6a3e; }
.segment-btn:disabled { opacity: 0.4; cursor: default; }
.apply-btn {
  margin-top: 6px; width: 100%; padding: 8px;
  background: #2a4a6e; border: 1px solid #4a7aae;
  border-radius: 5px; color: #adf; cursor: pointer; font-size: 12px;
}
.apply-btn:hover:not(:disabled) { background: #3a5a8e; }
.apply-btn:disabled { opacity: 0.4; cursor: default; }
.info-msg { margin-top: 6px; font-size: 11px; color: #8cf; }
.ok { margin-top: 6px; font-size: 11px; color: #6c6; }
</style>
