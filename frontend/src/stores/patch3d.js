import { defineStore } from 'pinia'
import { ref } from 'vue'

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

  // Prediction state
  const predicting        = ref(false)
  const segmenting        = ref(false)
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

  // Ground indices (class 2) — for Label GND+ button
  const groundIndices = ref([])

  // DTM grid from point cloud view — passed to backend for CHM-based segmentation
  // null when no class-2 ground points exist in the patch
  const dtmGrid = ref(null)  // { grid: float[], rows, cols, xMin, yMin, xRange, yRange }

  // Z bounds of the loaded patch — for elevation filter slider
  const zBoundsMin = ref(0)
  const zBoundsMax = ref(0)
  const elevFilterMin = ref(0)
  const elevFilterMax = ref(0)

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
    hasPrediction.value = false
    inferenceVersion.value = 'v1'
    predictionLegend.value  = []
    inferenceLabels.value   = null
    semanticLabels.value    = null
    segmentationPeaks.value = []
    segmentationSeedPeaks.value = []
    groundIndices.value = []
    dtmGrid.value = null
    zBoundsMin.value = 0
    zBoundsMax.value = 0
    elevFilterMin.value = 0
    elevFilterMax.value = 0
  }

  return {
    patchId, patchNumber, pointCount, nextLabel, selectedIndices, appliedLabels,
    savedUrl, lassoProcessing, viewMode, lastApplied,
    protectClasses, showAllLabels,
    predicting, segmenting, hasPrediction, predictionLegend,
    inferenceLabels, semanticLabels, inferenceVersion,
    segmentationPeaks, segmentationSeedPeaks,
    groundIndices, dtmGrid, zBoundsMin, zBoundsMax, elevFilterMin, elevFilterMax,
    addAppliedLabel, reset,
  }
})
