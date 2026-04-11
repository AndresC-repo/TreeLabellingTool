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

  function addRegion(region) {
    labeledRegions.value.push(region)
  }

  function removeRegion(patchId) {
    labeledRegions.value = labeledRegions.value.filter(r => r.patch_id !== patchId)
  }

  function clearActiveSelection() {
    activeSelection.value = null
  }

  function reset() {
    labeledRegions.value = []
    activeSelection.value = null
  }

  return {
    scalarField,
    activeTool,
    labeledRegions,
    activeSelection,
    addRegion,
    removeRegion,
    clearActiveSelection,
    reset,
  }
})
