<template>
  <div class="inference-legend">
    <h3>Inference <span class="ver" v-if="versionLabel">({{ versionLabel }})</span></h3>

    <!-- Legend swatches -->
    <div v-if="!store.predictionLegend.length" class="hint">No inference run yet</div>
    <div v-for="e in store.predictionLegend" :key="e.label" class="legend-row">
      <span class="swatch" :style="{ background: e.color }"></span>
      <span class="lbl">{{ e.label === 0 ? 'Non-tree' : e.name }}</span>
      <span class="cnt">{{ e.count.toLocaleString() }}</span>
    </div>

    <!-- Result message -->
    <p v-if="instMessage" class="info-msg">{{ instMessage }}</p>



    <!-- Lasso edit — shown when a lasso selection is active -->
    <div v-if="store.selectedIndices.length > 0 && store.inferenceLabels" class="inf-edit-section">
      <div class="inf-edit-header">{{ store.selectedIndices.length.toLocaleString() }} points selected</div>
      <div class="inf-edit-row">
        <select v-model.number="inferenceEditLabel" class="inf-edit-select">
          <option :value="0">Unclassify (remove)</option>
          <option v-for="e in store.predictionLegend.filter(e => e.label >= 201)" :key="e.label" :value="e.label">
            {{ e.name }}
          </option>
        </select>
        <button class="inf-edit-apply" @click="applyInferenceLabel(inferenceEditLabel)">Apply</button>
      </div>
      <button class="inf-edit-clear" @click="store.selectedIndices = []">Clear selection</button>
    </div>

    <!-- Step 1: semantic (tree / non-tree) -->
    <button
      class="semantic-btn"
      :disabled="semanticRunning || instRunning || store.segmenting"
      @click="runSemantic"
      title="Classify every point as tree or non-tree — no instance splitting"
    >
      {{ semanticRunning ? 'Running…' : 'Run Inference (tree / non-tree)' }}
    </button>

    <!-- Reset instances back to plain semantic coloring -->
    <button
      v-if="store.semanticLabels && store.hasPrediction"
      class="reset-semantic-btn"
      :disabled="instRunning || semanticRunning || applying"
      @click="resetToSemantic"
      title="Remove instance colours and go back to tree / non-tree view"
    >
      ↩ Back to Semantic View
    </button>

    <!-- Instance Segmentation Parameters — shown just above Run Instance Segmentation -->
    <div class="section-header" @click="instParamsOpen = !instParamsOpen">
      <span>⚙ Instance Segmentation Parameters</span>
      <span class="chevron">{{ instParamsOpen ? '▲' : '▼' }}</span>
    </div>
    <div v-if="instParamsOpen" class="params-grid">
      <label class="param-row">
        <span class="param-name" title="Mean-shift radius in metres. Roughly equal to the expected crown radius of the trees. Larger = fewer, bigger clusters.">Bandwidth (m)</span>
        <input v-model.number="instParams.bandwidth" type="number" min="0.5" max="20" step="0.5" class="param-input" />
      </label>
      <label class="param-row">
        <span class="param-name" title="Clusters with fewer points than this are discarded as noise.">Min pts / tree</span>
        <input v-model.number="instParams.min_points" type="number" min="1" step="50" class="param-input" />
      </label>
      <label class="param-row">
        <span class="param-name" title="How much the NN embedding features contribute relative to XY position. 0 = position only, 1+ = more NN influence.">Embed weight</span>
        <input v-model.number="instParams.embed_weight" type="number" min="0" max="2" step="0.05" class="param-input" />
      </label>
      <label class="param-row">
        <span class="param-name" title="Maximum distance (metres) a point can be from its cluster centre. Increase for large-crowned trees.">Max spread (m)</span>
        <input v-model.number="instParams.max_spread" type="number" min="1" max="30" step="1" class="param-input" />
      </label>
    </div>

    <!-- Primary action -->
    <button
      class="inst-btn"
      :disabled="!store.semanticLabels || instRunning || store.segmenting || applying"
      @click="runInstanceSegmentation"
      title="Split detected trees into individual instances (run inference first)"
    >
      {{ instRunning ? 'Running…' : 'Run Instance Segmentation' }}
    </button>

    <!-- Apply to Labels -->
    <button
      v-if="store.predictionLegend.length"
      class="apply-btn"
      :disabled="applying || store.segmenting || instRunning"
      @click="applyToLabels"
      title="Write inference results into the Labels layer so they can be saved"
    >
      {{ applying ? 'Applying…' : 'Apply to Labels' }}
    </button>
    <p v-if="applied" class="ok">Applied — switch to Labels view to verify</p>

    <!-- ── CHM Watershed ─────────────────────────────────────────────── -->
    <div class="section-divider">CHM Watershed</div>
    <p v-if="store.unitSource === 'uncertain'" class="units-warning" :title="unitTitle">
      ⚠ Units uncertain — this file may be in feet. Choose the right “Data units” in CHM params.
    </p>

      <div v-if="hasSemanticLabels" class="segment-section">
        <div class="section-header" @click="paramsOpen = !paramsOpen">
          <span>CHM params</span>
          <span class="header-right">
            <span
              class="help-btn"
              @click.stop="helpOpen = !helpOpen"
              :title="helpOpen ? 'Hide help' : 'What do these parameters do?'"
            >?</span>
            <span class="chevron">{{ paramsOpen ? '▲' : '▼' }}</span>
          </span>
        </div>

        <div v-if="helpOpen" class="help-box">
          <div class="help-row"><span class="help-name">Cell size</span><span class="help-desc">Size of each grid cell in metres. Smaller = more detail but slower. 1 m works well for most trees.</span></div>
          <div class="help-row"><span class="help-name">Smooth window</span><span class="help-desc">Blurs the height model before finding tree tops. Higher = fewer false splits in dense canopy.</span></div>
          <div class="help-row"><span class="help-name">Extra Gauss σ</span><span class="help-desc">Extra smoothing on top of the window filter. Leave at 0 unless the canopy is very noisy.</span></div>
          <div class="help-row"><span class="help-name">Min height</span><span class="help-desc">Every point lower than this above the terrain (DTM) is labelled non-tree — including trunks and low branches under a crown. Also the canopy floor for the watershed.</span></div>
          <div class="help-row"><span class="help-name">Min peak height</span><span class="help-desc">Minimum tree height. Tree tops lower than this are not used as seeds (grey dots): their canopy joins a touching tree, or becomes non-tree if isolated. Lets you keep a low canopy floor while ignoring short vegetation as separate trees.</span></div>
          <div class="help-row"><span class="help-name">Min tree spacing</span><span class="help-desc">Minimum distance between two tree tops, in metres. Roughly the smallest expected crown radius; larger values merge neighbouring trees.</span></div>
          <div class="help-row"><span class="help-name">Units</span><span class="help-desc">All values are in metres. If the file is in feet the tool converts them — check that the detected units are right.</span></div>
          <div class="help-row"><span class="help-name">Max radius</span><span class="help-desc">Tree points outside the canopy join the nearest tree top within this distance; the rest become non-tree.</span></div>
          <div class="help-row"><span class="help-name">Min pts / tree</span><span class="help-desc">Trees with fewer points than this are merged into the nearest larger tree.</span></div>
          <div class="help-row"><span class="help-name">Min blob area</span><span class="help-desc">Isolated canopy patches smaller than this area (m²) are treated as noise before segmentation. 0 = off. A single small tree crown is ~10–30 m².</span></div>
        </div>

        <div v-if="paramsOpen" class="params-grid">
          <!-- Data units: all params are metres; backend converts to the file's units -->
          <label class="param-row units-row" :title="unitTitle">
            <span class="param-name">Data units <span class="unit-src" :class="store.unitSource">{{ unitSourceLabel }}</span></span>
            <select class="param-input unit-select" :value="store.unitCode" :disabled="unitSaving" @change="changeUnits($event.target.value)">
              <option value="m">metres</option>
              <option value="ftUS">US survey ft</option>
              <option value="ft">int. feet</option>
            </select>
          </label>
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
            <span class="param-name" title="Duncanson uniform-filter window size (cells)">Smooth window (cells)</span>
            <input v-model.number="params.smooth_window" type="number" min="1" max="21" step="2" class="param-input" />
          </label>
          <label class="param-row">
            <span class="param-name" title="Optional extra Gaussian σ (0 = off)">Extra Gauss σ (cells)</span>
            <input v-model.number="params.smooth_sigma" type="number" min="0" max="10" step="0.5" class="param-input" />
          </label>
          <label class="param-row">
            <span class="param-name" title="Every point lower than this (m above the terrain) is labelled non-tree.">Min height (m)</span>
            <input v-model.number="params.min_height" type="number" min="0.5" max="30" step="0.5" class="param-input" />
          </label>
          <label class="param-row">
            <span class="param-name" title="Minimum tree height: local maxima lower than this (m above ground) are not used as seeds (grey dots). Their canopy joins a neighbouring tree if connected, otherwise becomes non-tree. Values below Min height are treated as Min height.">Min peak height (m)</span>
            <input v-model.number="params.min_peak_height" type="number" min="0.5" max="40" step="0.5" class="param-input" />
          </label>
          <label class="param-row">
            <span class="param-name" title="Minimum distance between two tree tops (m). Larger values merge neighbouring trees.">Min tree spacing (m)</span>
            <input v-model.number="params.min_tree_spacing" type="number" min="0.5" max="30" step="0.5" class="param-input" />
          </label>
          <label class="param-row">
            <span class="param-name" title="Tree points outside the canopy join the nearest tree top if it is within this XY distance (m)">Max radius (m)</span>
            <input v-model.number="params.max_radius" type="number" min="1" max="50" step="1" class="param-input" />
          </label>
          <label class="param-row">
            <span class="param-name" title="Instances with fewer points are merged into nearest larger tree">Min pts / tree</span>
            <input v-model.number="params.min_tree_points" type="number" min="1" step="50" class="param-input" />
          </label>
          <label class="param-row">
            <span class="param-name" title="Isolated canopy patches smaller than this area (m²) are treated as noise and become non-tree. Independent of cell size. 0 = off.">Min blob area (m²)</span>
            <input v-model.number="params.min_crown_area" type="number" min="0" step="1" class="param-input" />
          </label>
        </div>

        <button
          class="segment-btn"
          :disabled="store.segmenting || applying"
          @click="runSegmentation"
          title="Cluster tree points into individual instances using CHM local maxima"
        >
          {{ store.segmenting ? 'Segmenting…' : 'Segment Trees (CHM)' }}
        </button>
        <p v-if="instanceMessage" class="info-msg">{{ instanceMessage }}</p>
        <div v-if="segStats" class="seg-stats">
          <p v-if="segStats.warning" class="seg-warning">⚠ {{ segStats.warning }}</p>
          <div class="seg-row" title="Area of CHM cells at or above Min height">
            <span>Canopy</span>
            <span>{{ segStats.canopy_area_m2.toLocaleString() }} m²</span>
          </div>
          <div class="seg-row" title="Tree points lower than Min height above the terrain — set to non-tree">
            <span>Below min height → non-tree</span>
            <span>{{ segStats.points_below_min_height.toLocaleString() }} pts</span>
          </div>
          <div class="seg-row" title="Isolated canopy patches smaller than Min blob area">
            <span>Blobs removed</span>
            <span>{{ segStats.blobs_removed }} ({{ segStats.blob_points_removed.toLocaleString() }} pts)</span>
          </div>
          <div class="seg-row" title="Local maxima found above Min height">
            <span>Local maxima</span>
            <span>{{ segStats.peaks_found }}</span>
          </div>
          <div class="seg-row" title="Maxima rejected by Min peak height (grey dots)">
            <span>Below min peak height</span>
            <span>{{ segStats.peaks_below_peak_height }}</span>
          </div>
          <div class="seg-row" title="Basins with fewer than Min pts / tree, merged into neighbours">
            <span>Small basins merged</span>
            <span>{{ segStats.basins_merged }}</span>
          </div>
          <div class="seg-row" title="Tree points outside the canopy attached to a tree top within Max radius">
            <span>Joined via max radius</span>
            <span>{{ segStats.points_nn_assigned.toLocaleString() }} pts</span>
          </div>
          <div class="seg-row" title="Tree points that ended up as non-tree">
            <span>Tree pts → non-tree</span>
            <span>{{ segStats.points_unassigned.toLocaleString() }} ({{ pct(segStats.points_unassigned, segStats.tree_points) }})</span>
          </div>
        </div>
      </div>
      <div v-else class="hint">Run inference first to enable CHM segmentation</div>

      <!-- CHM marker legend -->
      <div v-if="store.segmentationSeedPeaks.length" class="marker-legend">
        <span class="marker-dot seed-dot"></span>
        <span class="marker-text">CHM seed (watershed start) — {{ store.segmentationSeedPeaks.length }}</span>
      </div>
      <div v-if="store.segmentationPeaks.length" class="marker-legend">
        <span class="marker-dot valid-dot"></span>
        <span class="marker-text">Valid tree top (after merge) — {{ store.segmentationPeaks.length }}</span>
      </div>
      <div v-if="store.segmentationRejectedPeaks.length" class="marker-legend">
        <span class="marker-dot rejected-dot"></span>
        <span class="marker-text">Below min peak height (not a seed) — {{ store.segmentationRejectedPeaks.length }}</span>
      </div>

      <!-- Crown metrics -->
      <button
        v-if="store.segmentationPeaks.length"
        class="metrics-btn"
        :disabled="metricsLoading"
        @click="runMetrics"
      >{{ metricsLoading ? 'Calculating…' : 'Calculate Crown Metrics' }}</button>

      <div v-if="treeMetrics.length" class="metrics-section">
        <div class="metrics-header">
          <span>Crown metrics — {{ treeMetrics.length }} trees</span>
          <button class="metrics-close" @click="treeMetrics = []">✕</button>
        </div>
        <div v-if="dtmSource !== 'external'" class="metrics-warn">
          No ground points — heights may be inaccurate
        </div>
        <div class="metrics-scroll">
          <table class="metrics-table">
            <thead>
              <tr>
                <th title="Tree instance number">#</th>
                <th title="Maximum height above terrain (m)">Ht (m)</th>
                <th title="Crown base height: 10th-percentile of point heights above terrain (m)">Hb (m)</th>
                <th title="Live crown length: Ht − Hb (m)">Lc (m)</th>
                <th title="Crown width: diameter of a circle with the same area as the crown footprint">CW (m)</th>
                <th title="Crown footprint area (m²)">CA (m²)</th>
                <th title="Number of LiDAR points in the tree">Pts</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in treeMetrics" :key="t.id">
                <td>{{ t.id - 200 }}</td>
                <td>{{ t.height }}</td>
                <td>{{ t.base_height }}</td>
                <td>{{ t.crown_length }}</td>
                <td>{{ t.crown_width }}</td>
                <td>{{ t.crown_area }}</td>
                <td>{{ t.point_count.toLocaleString() }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive } from 'vue'
import { useRoute } from 'vue-router'
import { usePatch3DStore } from '../../stores/patch3d.js'
import { applyLabelsBulk, segmentTrees, getTreeMetrics, predictInstances, predictPatch, dtmWorldParams, setUnits } from '../../api/client.js'

const emit = defineEmits(['segment-done', 'inference-edited', 'labels-bulk-applied'])

const route = useRoute()
const store = usePatch3DStore()

const VERSION_LABELS = { metric: 'Metric — XYZ (m)', finetune: 'Finetune — XYZ', finetune_int: 'Finetune — XYZ+I', scratch: 'Scratch — XYZ', scratch_int: 'Scratch — XYZ+I' }
const versionLabel = computed(() => VERSION_LABELS[store.inferenceVersion] ?? '')

const applying        = ref(false)
const semanticRunning = ref(false)
const applied         = ref(false)
const instRunning     = ref(false)
const instMessage     = ref('')
const instParamsOpen  = ref(false)
const paramsOpen      = ref(false)
const helpOpen        = ref(false)
const metricsLoading  = ref(false)
const treeMetrics     = ref([])
const instanceMessage = ref('')
const inferenceEditLabel = ref(0)

// Instance segmentation params (3-head)
const instParams = reactive({
  // Metres for every model (the backend converts for models trained in file units).
  // 2.5 m / 6 m ≈ the previous 8 / 20, which were effectively feet with the old models.
  bandwidth:    2.5,
  min_points:   450,
  embed_weight: 0.3,
  max_spread:   6.0,
})

// CHM segmentation hyperparameters
// All lengths in METRES (the backend converts to the file's units).
// Defaults tuned on a hand-labelled 34-tree FDEM patch (ARI 0.74).
const params = reactive({
  cell_size:        0.5,
  smooth_window:    1,
  smooth_sigma:     0.0,
  min_height:       2.5,
  min_peak_height:  2.5,
  min_tree_spacing: 4,
  max_radius:       1.0,
  min_tree_points:  300,
  // Was "min_crown_cells: 70": at 1.5 m cells that is 157 m², which deleted most isolated trees
  min_crown_area:   5,
})

// What each segmentation step did (from the backend), shown under the button
const segStats = ref(null)

// ── Data units ──
const unitSaving = ref(false)
const unitSourceLabel = computed(() => ({ crs: 'from file', guess: 'guessed', user: 'set by you', default: 'assumed', uncertain: 'uncertain — check' })[store.unitSource] ?? '')
const unitTitle = computed(() =>
  store.unitSource === 'crs'   ? 'Read from the coordinate system stored in the LAS file.' :
  store.unitSource === 'guess' ? 'The file has no coordinate system. Coordinates look like US state plane in feet — change this if wrong.' :
  store.unitSource === 'user'  ? 'Set manually for this file.' :
  store.unitSource === 'uncertain' ? 'No coordinate system, and read as metres the point density would be implausibly low (< 4 pts/m²). The data may be in feet. Metres are assumed until you choose; exports carry no units marker until then.' :
  'The file has no coordinate system; metres assumed. Change this if the data is in feet.')

async function changeUnits(code) {
  if (code === store.unitCode) return
  unitSaving.value = true
  try {
    const res = await setUnits(route.params.id, code)
    store.unitCode = res.data.code; store.unitScale = res.data.scale; store.unitSource = res.data.source
    instanceMessage.value = `Units set to ${res.data.name} — run segmentation again.`
  } catch (err) {
    console.error('Setting units failed:', err)
    instanceMessage.value = 'Could not change units — see console'
  } finally {
    unitSaving.value = false
  }
}
const pct = (n, total) => total ? `${Math.round(100 * n / total)}%` : '0%'


// CHM requires semantic labels (0/101) — available after either flow
const hasSemanticLabels = computed(() => store.semanticLabels !== null)
const dtmSource = computed(() => store.dtmGrid ? 'external' : 'fallback')

// Mirrors paletteColor() in usePointCloud3D.js
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

function applyInferenceLabel(targetLabel) {
  if (!store.inferenceLabels || !store.selectedIndices.length) return
  const newLabels = Array.from(store.inferenceLabels)
  for (const i of store.selectedIndices) newLabels[i] = targetLabel
  store.inferenceLabels = newLabels

  const counts = {}
  for (const lbl of newLabels) counts[lbl] = (counts[lbl] || 0) + 1
  store.predictionLegend = store.predictionLegend
    .map(e => ({ ...e, count: counts[e.label] ?? 0 }))
    .filter(e => e.count > 0)

  store.selectedIndices = []
  emit('inference-edited', newLabels)
}

async function runSemantic() {
  if (semanticRunning.value) return
  semanticRunning.value = true
  try {
    const res = await predictPatch(
      route.params.id,
      route.params.patchId,
      store.inferenceVersion,
    )
    const labels = new Int32Array(res.data.labels)
    store.inferenceLabels  = labels
    store.semanticLabels   = labels
    store.hasPrediction    = true
    store.viewMode         = 'prediction'
    emit('segment-done', labels)
  } catch (err) {
    console.error('Semantic inference failed:', err)
  } finally {
    semanticRunning.value = false
  }
}

function resetToSemantic() {
  if (!store.semanticLabels) return
  store.inferenceLabels = store.semanticLabels
  store.viewMode        = 'prediction'
  emit('segment-done', store.semanticLabels)
}

async function runInstanceSegmentation() {
  if (instRunning.value) return
  instRunning.value = true
  instMessage.value = ''
  applied.value = false
  store.segmentationPeaks = []
  store.segmentationSeedPeaks = []
  store.segmentationRejectedPeaks = []
  segStats.value = null
  try {
    const res = await predictInstances(
      route.params.id,
      route.params.patchId,
      store.inferenceVersion,
      instParams,
    )
    const { labels, n_instances } = res.data
    store.inferenceLabels = labels
    // Synthesise semantic labels for CHM (Advanced): instance >= 201 → 101 (tree), else 0
    store.semanticLabels = labels.map(l => l >= 201 ? 101 : 0)

    const counts = {}
    for (const lbl of labels) counts[lbl] = (counts[lbl] || 0) + 1

    store.predictionLegend = Object.entries(counts)
      .sort(([a], [b]) => Number(a) - Number(b))
      .map(([lbl, count]) => ({
        label: Number(lbl),
        name:  Number(lbl) === 0 ? 'Non-tree' : `Tree #${Number(lbl) - 200}`,
        color: _paletteHex(Number(lbl)),
        count,
      }))

    instMessage.value = n_instances === 0
      ? 'No instances found'
      : `${n_instances} tree instance${n_instances > 1 ? 's' : ''} found`

    emit('segment-done', labels)
  } catch (err) {
    console.error('Instance segmentation failed:', err)
    instMessage.value = `Failed: ${err.response?.data?.detail ?? err.message}`
  } finally {
    instRunning.value = false
  }
}

async function runSegmentation() {
  if (!store.semanticLabels || store.segmenting) return
  store.segmenting = true
  instanceMessage.value = ''
  applied.value = false
  store.segmentationPeaks = []
  store.segmentationSeedPeaks = []
  store.segmentationRejectedPeaks = []
  segStats.value = null
  try {
    const payload = { ...params, ...(store.dtmGrid ? dtmWorldParams(store.dtmGrid) : {}) }

    const res = await segmentTrees(
      route.params.id,
      route.params.patchId,
      Array.from(store.semanticLabels),
      payload,
    )
    const { labels, tree_count } = res.data

    store.inferenceLabels       = labels
    store.segmentationPeaks     = res.data.peaks
    store.segmentationSeedPeaks = res.data.seed_peaks ?? []
    store.segmentationRejectedPeaks = res.data.rejected_peaks ?? []
    segStats.value = res.data.stats ?? null

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
    if (tree_count > 0)
      instanceMessage.value += ` — ${store.segmentationSeedPeaks.length} CHM seeds, ${store.segmentationPeaks.length} valid peaks`

    emit('segment-done', labels)
  } catch (err) {
    console.error('CHM segmentation failed:', err)
    instanceMessage.value = 'Segmentation failed — see console'
  } finally {
    store.segmenting = false
  }
}

async function runMetrics() {
  if (!store.inferenceLabels || metricsLoading.value) return
  metricsLoading.value = true
  try {
    const res = await getTreeMetrics(
      route.params.id,
      route.params.patchId,
      Array.from(store.inferenceLabels),
      params.cell_size,
      store.dtmGrid || null,
    )
    treeMetrics.value = res.data.trees
  } catch (err) {
    console.error('Crown metrics failed:', err)
  } finally {
    metricsLoading.value = false
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
    emit('labels-bulk-applied', store.inferenceLabels)
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
.hint { font-size: 12px; color: #556; margin-bottom: 6px; }
.ver { font-size: 11px; color: #778; font-weight: normal; }

/* ── Section headers ──────────────────────────────────────────── */
.section-header {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 11px; color: #88a; cursor: pointer;
  padding: 4px 0; border-bottom: 1px solid #223;
  user-select: none; margin: 8px 0 4px;
}
.section-header:hover { color: #aad; }
.header-right { display: flex; align-items: center; gap: 6px; }
.chevron { font-size: 10px; }

.help-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 14px; height: 14px; border-radius: 50%;
  background: #334; border: 1px solid #556;
  color: #99b; font-size: 9px; font-weight: bold;
  cursor: pointer; line-height: 1; flex-shrink: 0;
}
.help-btn:hover { background: #445; border-color: #778; color: #ccf; }

.help-box {
  background: #0a1020; border: 1px solid #2a3050;
  border-radius: 5px; padding: 8px 10px;
  display: flex; flex-direction: column; gap: 6px; margin-bottom: 6px;
}
.help-row { display: flex; gap: 8px; font-size: 10px; line-height: 1.4; }
.help-name { color: #99c; font-weight: 600; white-space: nowrap; min-width: 80px; flex-shrink: 0; }
.help-desc { color: #778; }

/* ── Params grid ──────────────────────────────────────────────── */
.params-grid {
  display: flex; flex-direction: column; gap: 4px;
  background: #0e1220; border: 1px solid #223;
  border-radius: 5px; padding: 8px 10px; margin-bottom: 8px;
}
.param-row {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 11px; color: #88a; gap: 6px;
}
.param-name { flex: 1; cursor: help; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.param-input {
  width: 68px; background: #1e2840; color: #eee;
  border: 1px solid #445; border-radius: 4px;
  padding: 3px 6px; font-size: 11px; text-align: right; flex-shrink: 0;
}
.param-input:focus { outline: none; border-color: #6a9adf; }

/* ── Primary action button ────────────────────────────────────── */
.semantic-btn {
  width: 100%; padding: 10px;
  background: #1e4a2e; border: 1px solid #3a7a4e;
  border-radius: 6px; color: #8de8a8; cursor: pointer; font-size: 14px;
  margin-bottom: 6px;
}
.semantic-btn:hover:not(:disabled) { background: #2a6a3e; }
.semantic-btn:disabled { opacity: 0.4; cursor: default; }

.reset-semantic-btn {
  width: 100%; padding: 7px;
  background: #1e2e1e; border: 1px solid #3a5a3a;
  border-radius: 6px; color: #6ab87a; cursor: pointer; font-size: 12px;
  margin-bottom: 6px;
}
.reset-semantic-btn:hover:not(:disabled) { background: #253525; }
.reset-semantic-btn:disabled { opacity: 0.4; cursor: default; }

.inst-btn {
  width: 100%; padding: 9px; margin-top: 4px;
  background: #1a3a5e; border: 1px solid #3a6aae;
  border-radius: 5px; color: #adf; cursor: pointer; font-size: 13px; font-weight: 600;
}
.inst-btn:hover:not(:disabled) { background: #2a4e80; }
.inst-btn:disabled { opacity: 0.4; cursor: default; }

/* ── Apply button ─────────────────────────────────────────────── */
.apply-btn {
  margin-top: 6px; width: 100%; padding: 8px;
  background: #2a4a6e; border: 1px solid #4a7aae;
  border-radius: 5px; color: #adf; cursor: pointer; font-size: 12px;
}
.apply-btn:hover:not(:disabled) { background: #3a5a8e; }
.apply-btn:disabled { opacity: 0.4; cursor: default; }

.info-msg { margin-top: 6px; font-size: 11px; color: #8cf; }
.ok { margin-top: 6px; font-size: 11px; color: #6c6; }

/* ── CHM Watershed divider ────────────────────────────────────── */
.section-divider {
  display: flex; align-items: center;
  font-size: 11px; color: #7ab; font-weight: 600;
  letter-spacing: 0.5px; text-transform: uppercase;
  padding: 6px 0 4px; border-top: 1px solid #2a3a5a; margin-top: 12px;
}

/* ── CHM segment section (inside Advanced) ────────────────────── */
.segment-section { display: flex; flex-direction: column; gap: 6px; }

.dtm-badge {
  display: flex; align-items: center; gap: 6px;
  font-size: 10px; padding: 4px 8px;
  border-radius: 4px; margin-bottom: 4px;
}
.dtm-ok       { background: #0d2a18; color: #6c6; border: 1px solid #2a6a3a; }
.dtm-fallback { background: #2a1a08; color: #c84; border: 1px solid #6a3a10; }
.dtm-icon { font-weight: bold; }

.segment-btn {
  width: 100%; padding: 8px;
  background: #1a4a2e; border: 1px solid #3a8a4e;
  border-radius: 5px; color: #afd; cursor: pointer; font-size: 12px;
}
.segment-btn:hover:not(:disabled) { background: #2a6a3e; }
.segment-btn:disabled { opacity: 0.4; cursor: default; }

/* ── CHM marker legend ────────────────────────────────────────── */
.marker-legend {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; color: #889;
}
.marker-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.seed-dot  { background: #ffcc00; box-shadow: 0 0 4px #ffcc00; }
.valid-dot { background: #ff3030; box-shadow: 0 0 4px #ff4040; }
.rejected-dot { background: #8a8a9a; box-shadow: 0 0 3px #8a8a9a; }

/* ── Segmentation step summary ───────────────────────────────── */
.seg-stats {
  margin-top: 6px; padding: 6px 8px;
  background: rgba(0,0,0,0.25); border: 1px solid #2a3a5a; border-radius: 5px;
  display: flex; flex-direction: column; gap: 2px;
}
.seg-row { display: flex; justify-content: space-between; gap: 8px; font-size: 11px; color: #889; cursor: help; }
.seg-row span:last-child { color: #bcd; font-variant-numeric: tabular-nums; }
.seg-warning { font-size: 11px; color: #fb4; margin-bottom: 4px; line-height: 1.4; }
.units-row { cursor: help; }
.unit-select { width: auto; min-width: 104px; }
.unit-src { font-size: 10px; padding: 0 4px; border-radius: 3px; margin-left: 2px; }
.unit-src.crs { color: #7c9; }
.unit-src.guess { color: #fb4; }
.unit-src.user { color: #8cf; }
.unit-src.default { color: #889; }
.unit-src.uncertain { color: #f96; }
.units-warning {
  font-size: 11px; line-height: 1.4; color: #fc8; cursor: help;
  background: rgba(255,150,60,0.08); border: 1px solid #7a4a2a; border-radius: 5px;
  padding: 5px 8px; margin: 4px 0 6px;
}
.marker-text { color: #778; }

/* ── Crown metrics ────────────────────────────────────────────── */
.metrics-btn {
  width: 100%; padding: 7px;
  background: #1a3a4a; border: 1px solid #3a7a9a;
  border-radius: 5px; color: #9df; cursor: pointer; font-size: 12px;
}
.metrics-btn:hover:not(:disabled) { background: #2a5a6a; }
.metrics-btn:disabled { opacity: 0.4; cursor: default; }

.metrics-section {
  background: #0a1020; border: 1px solid #2a3050;
  border-radius: 5px; overflow: hidden;
}
.metrics-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 5px 8px; background: #111828;
  font-size: 11px; color: #99c;
}
.metrics-close { background: none; border: none; color: #556; cursor: pointer; font-size: 11px; padding: 0 2px; }
.metrics-close:hover { color: #aac; }
.metrics-warn { font-size: 10px; color: #c84; background: #1a0e04; padding: 4px 8px; border-bottom: 1px solid #2a1a08; }
.metrics-scroll { overflow-x: auto; max-height: 220px; overflow-y: auto; }
.metrics-table { width: 100%; border-collapse: collapse; font-size: 10px; color: #ccd; }
.metrics-table th {
  position: sticky; top: 0;
  background: #151e30; color: #889; font-weight: 600;
  padding: 4px 5px; text-align: right; white-space: nowrap;
  border-bottom: 1px solid #2a3050; cursor: help;
}
.metrics-table th:first-child { text-align: center; }
.metrics-table td { padding: 3px 5px; text-align: right; border-bottom: 1px solid #161e2e; }
.metrics-table td:first-child { text-align: center; color: #99c; font-weight: 600; }
.metrics-table tbody tr:hover { background: #141c2c; }

/* ── Lasso edit ───────────────────────────────────────────────── */
.inf-edit-section {
  margin: 8px 0; padding: 8px 10px;
  background: #1a1a2e; border: 1px solid #4a4a7a;
  border-radius: 5px; display: flex; flex-direction: column; gap: 6px;
}
.inf-edit-header { font-size: 11px; color: #aac; font-weight: 600; }
.inf-edit-row { display: flex; gap: 6px; align-items: center; }
.inf-edit-select {
  flex: 1; background: #12122a; color: #eee;
  border: 1px solid #445; border-radius: 4px;
  padding: 4px 6px; font-size: 11px;
}
.inf-edit-apply {
  padding: 4px 10px; background: #2a2a5e; border: 1px solid #5a5aae;
  border-radius: 4px; color: #aaf; cursor: pointer; font-size: 11px; white-space: nowrap;
}
.inf-edit-apply:hover { background: #3a3a7e; }
.inf-edit-clear { font-size: 10px; color: #667; background: none; border: none; cursor: pointer; text-align: left; padding: 0; }
.inf-edit-clear:hover { color: #99b; }
</style>
