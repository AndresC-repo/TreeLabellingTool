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

  function addAppliedLabel(labelValue) {
    if (!appliedLabels.value.includes(labelValue)) {
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
  }

  return { patchId, patchNumber, pointCount, nextLabel, selectedIndices, appliedLabels, savedUrl, lassoProcessing, viewMode, lastApplied, addAppliedLabel, reset }
})
