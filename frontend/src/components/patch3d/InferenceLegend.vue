<template>
  <div class="inference-legend">
    <h3>Inference <span class="ver" v-if="versionLabel">({{ versionLabel }})</span></h3>
    <div v-if="!store.predictionLegend.length" class="hint">No inference run yet</div>
    <div v-for="e in store.predictionLegend" :key="e.label" class="legend-row">
      <span class="swatch" :style="{ background: e.color }"></span>
      <span class="lbl">{{ e.label }} — {{ e.name }}</span>
      <span class="cnt">{{ e.count.toLocaleString() }}</span>
    </div>

    <!-- Segmentation controls — shown once inference results exist -->
    <div v-if="hasTreeLabel" class="segment-section">
      <div class="section-header" @click="paramsOpen = !paramsOpen">
        <span>Segmentation params</span>
        <span class="chevron">{{ paramsOpen ? '▲' : '▼' }}</span>
      </div>

      <div v-if="paramsOpen" class="params-grid">
        <!-- DTM source indicator -->
        <div class="dtm-badge" :class="dtmSource === 'external' ? 'dtm-ok' : 'dtm-fallback'">
          <span class="dtm-icon">{{ dtmSource === 'external' ? '✓' : '!' }}</span>
          <span v-if="dtmSource === 'external'">Using DTM from point cloud view</span>
          <span v-else>No ground points — using Z minimum fallback</span>
        </div>

        <label class="param-row">
          <span class="param-name" title="CHM grid cell size in metres">Cell size (m)</span>
          <input v-model.number="params.cell_size" type="number" min="0.1" max="5" step="0.1" class="param-input" />
        </label>
        <label class="param-row">
          <span class="param-name" title="Duncanson uniform-filter window size (cells). Paper default: 5. Larger = smoother CHM, fewer over-split crowns.">Smooth window (cells)</span>
          <input v-model.number="params.smooth_window" type="number" min="1" max="21" step="2" class="param-input" />
        </label>
        <label class="param-row">
          <span class="param-name" title="Optional extra Gaussian σ applied after the uniform filter (0 = off). Use only for very noisy data.">Extra Gauss σ (cells)</span>
          <input v-model.number="params.smooth_sigma" type="number" min="0" max="10" step="0.5" class="param-input" />
        </label>
        <label class="param-row">
          <span class="param-name" title="Minimum CHM height in metres for a local maximum to be kept as a tree top">Min height (m)</span>
          <input v-model.number="params.min_height" type="number" min="0.5" max="30" step="0.5" class="param-input" />
        </label>
        <label class="param-row">
          <span class="param-name" title="Size of the neighbourhood (in cells) used for local maximum detection. Controls minimum separation between tree tops.">Peak window (cells)</span>
          <input v-model.number="params.min_distance" type="number" min="1" max="50" step="1" class="param-input" />
        </label>
        <label class="param-row">
          <span class="param-name" title="Maximum XY distance (metres) from a seed peak to assign a tree point. Points beyond this are assigned to the nearest ungrouped cluster.">Max radius (m)</span>
          <input v-model.number="params.max_radius" type="number" min="1" max="50" step="1" class="param-input" />
        </label>
        <label class="param-row">
          <span class="param-name" title="Instances with fewer points than this are merged into the nearest valid (larger) tree.">Min pts / tree</span>
          <input v-model.number="params.min_tree_points" type="number" min="1" step="10" class="param-input" />
        </label>
      </div>

      <button
        class="segment-btn"
        :disabled="store.segmenting || applying"
        @click="runSegmentation"
        title="Cluster tree points into individual instances using CHM local maxima"
      >
        {{ store.segmenting ? 'Segmenting…' : 'Segment Tree Instances' }}
      </button>
    </div>

    <!-- Marker legend (shown once segmentation has been run) -->
    <div v-if="store.segmentationSeedPeaks.length" class="marker-legend">
      <span class="marker-dot seed-dot"></span>
      <span class="marker-text">CHM seed (watershed start) — {{ store.segmentationSeedPeaks.length }}</span>
    </div>
    <div v-if="store.segmentationPeaks.length" class="marker-legend">
      <span class="marker-dot valid-dot"></span>
      <span class="marker-text">Valid tree top (after merge) — {{ store.segmentationPeaks.length }}</span>
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
import { ref, computed, reactive } from 'vue'
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
const paramsOpen      = ref(false)

// Segmentation hyperparameters — all editable via UI
const params = reactive({
  cell_size:       0.5,
  smooth_window:   5,
  smooth_sigma:    0.0,
  min_height:      2.0,
  min_distance:    5,
  max_radius:      15.0,
  min_tree_points: 50,
})

// Show segment controls as long as we have inference data
const hasTreeLabel = computed(() => store.inferenceLabels !== null)

// DTM source indicator: 'external' when the point cloud view has ground points
const dtmSource = computed(() => store.dtmGrid ? 'external' : 'fallback')

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
  store.segmentationPeaks = []
  store.segmentationSeedPeaks = []
  try {
    // Build request payload — include DTM grid from point cloud view if available
    const payload = { ...params }
    if (store.dtmGrid) {
      payload.dtm_grid   = store.dtmGrid.grid
      payload.dtm_rows   = store.dtmGrid.rows
      payload.dtm_cols   = store.dtmGrid.cols
      payload.dtm_x_min  = store.dtmGrid.xMin
      payload.dtm_y_min  = store.dtmGrid.yMin
      payload.dtm_x_range = store.dtmGrid.xRange
      payload.dtm_y_range = store.dtmGrid.yRange
    }

    const res = await segmentTrees(
      route.params.id,
      route.params.patchId,
      Array.from(store.semanticLabels),   // always use original 0/101 labels
      payload,
    )
    const { labels, tree_count } = res.data

    store.inferenceLabels       = labels
    store.segmentationPeaks     = res.data.peaks
    store.segmentationSeedPeaks = res.data.seed_peaks ?? []

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
    // Scroll info into view
    instanceMessage.value +=
      tree_count > 0
        ? ` — ${store.segmentationSeedPeaks.length} CHM seeds (yellow), ${store.segmentationPeaks.length} valid peaks (red)`
        : ''
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

/* ── Segmentation section ─────────────────────────────────────── */
.segment-section {
  margin-top: 10px;
  display: flex; flex-direction: column; gap: 6px;
}

.section-header {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 11px; color: #88a; cursor: pointer;
  padding: 4px 0; border-bottom: 1px solid #223;
  user-select: none;
}
.section-header:hover { color: #aad; }
.chevron { font-size: 10px; }

.params-grid {
  display: flex; flex-direction: column; gap: 4px;
  background: #0e1220; border: 1px solid #223;
  border-radius: 5px; padding: 8px 10px;
}

/* DTM source badge */
.dtm-badge {
  display: flex; align-items: center; gap: 6px;
  font-size: 10px; padding: 4px 8px;
  border-radius: 4px; margin-bottom: 4px;
}
.dtm-ok       { background: #0d2a18; color: #6c6; border: 1px solid #2a6a3a; }
.dtm-fallback { background: #2a1a08; color: #c84; border: 1px solid #6a3a10; }
.dtm-icon { font-weight: bold; }

.param-row {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 11px; color: #88a; gap: 6px;
}
.param-name {
  flex: 1; cursor: help;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.param-input {
  width: 68px; background: #1e2840; color: #eee;
  border: 1px solid #445; border-radius: 4px;
  padding: 3px 6px; font-size: 11px; text-align: right;
  flex-shrink: 0;
}
.param-input:focus { outline: none; border-color: #6a9adf; }

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
.marker-legend {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; color: #889; margin-top: 4px;
}
.marker-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
}
.seed-dot  { background: #ffcc00; box-shadow: 0 0 4px #ffcc00; }
.valid-dot { background: #ff3030; box-shadow: 0 0 4px #ff4040; }
.marker-text { color: #778; }

.info-msg { margin-top: 6px; font-size: 11px; color: #8cf; }
.ok { margin-top: 6px; font-size: 11px; color: #6c6; }
</style>
