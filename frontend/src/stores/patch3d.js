import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export const usePatch3DStore = defineStore('patch3d', () => {
  const patchId = ref(null)
  const patchNumber = ref(1)
  const pointCount = ref(0)
  const nextLabel = ref(101)
  const selectedIndices = ref([])
  const appliedLabels = ref([])   // sorted unique label values applied this session
  const savedUrl = ref(null)
  const lassoProcessing = ref(false)
  const viewMode = ref('elevation')
  const lastApplied = ref(null)   // { indices: number[], labelValue: number }

  // Label protection setting — persists across patches in the session
  const protectClasses    = ref(true)   // when true, skip ASPRS class 2 & 6 when labeling
  // Classification view setting — persists across patches in the session
  const showAllLabels     = ref(true)   // when true, color all labels; false = only ASPRS < 100
  // Base ground label value — used by Label GND button and DTM "Label as GND" action
  const baseGround        = ref(2)

  // Prediction state
  const predicting        = ref(false)
  const segmenting        = ref(false)
  const isWholePatch      = ref(false)
  const hasPrediction     = ref(false)
  const inferenceVersion  = ref('v1')   // 'v1' | 'v2'
  // [{ label: number, name: string, color: string, count: number }]
  const predictionLegend = ref([])
  // Raw per-point label array from last inference (Int32Array or plain array)
  const inferenceLabels     = ref(null)
  // Original 0/101 semantic labels from inference — never overwritten by segmentation
  const semanticLabels      = ref(null)
  // [[x,y,z], ...] valid tree-top positions (after merge filter)
  const segmentationPeaks   = ref([])
  // [[x,y,z], ...] ALL CHM local maxima used as watershed seeds (for visualisation)
  const segmentationSeedPeaks = ref([])
  // [[x,y,z], ...] local maxima rejected by min peak height (grey dots)
  const segmentationRejectedPeaks = ref([])

  // Undo signal — set after a successful undo to trigger color rebuild in CanvasRenderer3D
  const undoResult = ref(null)   // { full_reload, indices, label_values } | null

  // Ground indices (class 2) — for Label GND+ button
  const groundIndices = ref([])

  // DTM grid from point cloud view — passed to backend for CHM-based segmentation
  // null when no class-2 ground points exist in the patch
  // World x/y of the 3D view's local origin (positions are relative to it)
  const originX = ref(0)
  const originY = ref(0)
  // Linear units of the data. All segmentation settings are in metres; the backend
  // converts them. unitScale = metres per data unit (0.3048006 for US survey feet).
  const unitCode   = ref('m')
  const unitScale  = ref(1)
  const unitSource = ref('default')   // crs | guess | default | user
  const dtmGrid = ref(null)  // { grid: float[], rows, cols, xMin, yMin, xRange, yRange }

  // Z bounds of the loaded patch — for elevation filter slider
  const zBoundsMin = ref(0)
  const zBoundsMax = ref(0)
  const elevFilterMin = ref(0)
  const elevFilterMax = ref(0)

  // XY bounds — set on load, used by ClipPanel
  const xBoundsMin = ref(0)
  const xBoundsMax = ref(0)
  const yBoundsMin = ref(0)
  const yBoundsMax = ref(0)
  // Clip filter — ClipPanel writes these, CanvasRenderer3D watches and calls setClipFilter
  const xClipMin = ref(0)
  const xClipMax = ref(0)
  const yClipMin = ref(0)
  const yClipMax = ref(0)
  const zClipMin = ref(0)
  const zClipMax = ref(0)
  const clipActive = ref(false)

  // Bumped on every label change (apply, undo, redo, bulk apply) so panels can refresh
  // things that depend on the labels (undo/redo depth, tree count in the file name).
  const labelsVersion = ref(0)
  function bumpLabels() { labelsVersion.value++ }
  watch([lastApplied, undoResult], () => { labelsVersion.value++ })

  function addAppliedLabel(labelValue) {
    if (labelValue !== 0 && !appliedLabels.value.includes(labelValue)) {
      appliedLabels.value = [...appliedLabels.value, labelValue].sort((a, b) => a - b)
    }
  }

  function reset() {
    patchId.value = null
    patchNumber.value = 1
    pointCount.value = 0
    nextLabel.value = 101
    selectedIndices.value = []
    appliedLabels.value = []
    savedUrl.value = null
    lassoProcessing.value = false
    viewMode.value = 'elevation'
    lastApplied.value = null
    predicting.value = false
    segmenting.value = false
    isWholePatch.value = false
    hasPrediction.value = false
    inferenceVersion.value = 'v1'
    predictionLegend.value  = []
    inferenceLabels.value   = null
    semanticLabels.value    = null
    segmentationPeaks.value = []
    segmentationSeedPeaks.value = []
    segmentationRejectedPeaks.value = []
    undoResult.value = null
    groundIndices.value = []
    dtmGrid.value = null
    originX.value = 0
    originY.value = 0
    unitCode.value = 'm'; unitScale.value = 1; unitSource.value = 'default'
    zBoundsMin.value = 0
    zBoundsMax.value = 0
    elevFilterMin.value = 0
    elevFilterMax.value = 0
    xBoundsMin.value = 0; xBoundsMax.value = 0
    yBoundsMin.value = 0; yBoundsMax.value = 0
    xClipMin.value = 0; xClipMax.value = 0
    yClipMin.value = 0; yClipMax.value = 0
    zClipMin.value = 0; zClipMax.value = 0
    clipActive.value = false
  }

  return {
    patchId, patchNumber, pointCount, nextLabel, selectedIndices, appliedLabels,
    labelsVersion, bumpLabels,
    savedUrl, lassoProcessing, viewMode, lastApplied,
    protectClasses, showAllLabels, baseGround,
    predicting, segmenting, isWholePatch, hasPrediction, predictionLegend,
    inferenceLabels, semanticLabels, inferenceVersion,
    segmentationPeaks, segmentationSeedPeaks, segmentationRejectedPeaks,
    undoResult, groundIndices, dtmGrid, originX, originY, unitCode, unitScale, unitSource, zBoundsMin, zBoundsMax, elevFilterMin, elevFilterMax,
    xBoundsMin, xBoundsMax, yBoundsMin, yBoundsMax,
    xClipMin, xClipMax, yClipMin, yClipMax, zClipMin, zClipMax, clipActive,
    addAppliedLabel, reset,
  }
})
