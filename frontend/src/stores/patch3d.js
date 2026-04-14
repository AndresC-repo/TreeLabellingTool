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

  // Prediction state
  const predicting    = ref(false)
  const hasPrediction = ref(false)

  // Ground indices (class 2) — for Label GND+ button
  const groundIndices = ref([])

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
    hasPrediction.value = false
    groundIndices.value = []
    zBoundsMin.value = 0
    zBoundsMax.value = 0
    elevFilterMin.value = 0
    elevFilterMax.value = 0
  }

  return {
    patchId, patchNumber, pointCount, nextLabel, selectedIndices, appliedLabels,
    savedUrl, lassoProcessing, viewMode, lastApplied,
    predicting, hasPrediction,
    groundIndices, zBoundsMin, zBoundsMax, elevFilterMin, elevFilterMax,
    addAppliedLabel, reset,
  }
})
