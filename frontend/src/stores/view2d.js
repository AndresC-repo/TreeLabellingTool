import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'

export const useView2DStore = defineStore('view2d', () => {
  const scalarField = ref('elevation')
  // 'rectangle' | 'freehand' | 'fixed'
  const activeTool = ref('rectangle')
  // Array of { patch_id, selection_type, bounds_2d?, polygon_2d?, point_count, svgPoints? }
  const labeledRegions = ref([])
  // Current active selection (for SVG overlay rendering)
  const activeSelection = shallowRef(null)
  // Set of patch_ids that have had at least one label applied
  const labelledPatchIds = ref(new Set())

  function addRegion(region) {
    labeledRegions.value.push(region)
  }

  function removeRegion(patchId) {
    labeledRegions.value = labeledRegions.value.filter(r => r.patch_id !== patchId)
  }

  function markLabelled(patchId) {
    if (!labelledPatchIds.value.has(patchId)) {
      labelledPatchIds.value = new Set([...labelledPatchIds.value, patchId])
    }
  }

  function clearActiveSelection() {
    activeSelection.value = null
  }

  function reset() {
    labeledRegions.value = []
    activeSelection.value = null
    labelledPatchIds.value = new Set()
  }

  return {
    scalarField,
    activeTool,
    labeledRegions,
    activeSelection,
    labelledPatchIds,
    addRegion,
    removeRegion,
    markLabelled,
    clearActiveSelection,
    reset,
  }
})
