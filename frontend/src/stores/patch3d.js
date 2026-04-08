import { defineStore } from 'pinia'
import { ref } from 'vue'

export const usePatch3DStore = defineStore('patch3d', () => {
  const patchId = ref(null)
  const pointCount = ref(0)
  const nextLabel = ref(101)
  const selectedIndices = ref([])
  const savedUrl = ref(null)

  function reset() {
    patchId.value = null
    pointCount.value = 0
    nextLabel.value = 101
    selectedIndices.value = []
    savedUrl.value = null
  }

  return { patchId, pointCount, nextLabel, selectedIndices, savedUrl, reset }
})
