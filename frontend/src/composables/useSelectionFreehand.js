import * as THREE from 'three'
import { ref } from 'vue'

/**
 * Freehand polygon selection tool.
 * Left-click adds points; right-click closes the polygon.
 */
export function useSelectionFreehand(camera, rendererDomEl) {
  const drawing = ref(false)
  // SVG-space points: [{x, y}]
  const svgPoints = ref([])

  function screenToWorld(clientX, clientY) {
    const el = rendererDomEl.value
    const r = el.getBoundingClientRect()
    const ndcX = ((clientX - r.left) / r.width)  * 2 - 1
    const ndcY = -((clientY - r.top)  / r.height) * 2 + 1
    const vec = new THREE.Vector3(ndcX, ndcY, 0)
    vec.unproject(camera.value)
    return { x: vec.x, y: vec.y }
  }

  function onClick(e) {
    if (e.button !== 0) return
    drawing.value = true
    svgPoints.value.push({ x: e.offsetX, y: e.offsetY })
  }

  /**
   * Close the polygon on right-click.
   * @returns {Array<[number, number]> | null} world-space polygon or null if too few points
   */
  function onContextMenu(e) {
    e.preventDefault()
    if (!drawing.value || svgPoints.value.length < 3) {
      svgPoints.value = []
      drawing.value = false
      return null
    }
    drawing.value = false
    const el = rendererDomEl.value
    const r = el.getBoundingClientRect()
    const worldPoly = svgPoints.value.map(p => {
      const w = screenToWorld(p.x + r.left, p.y + r.top)
      return [w.x, w.y]
    })
    svgPoints.value = []
    return worldPoly
  }

  function cancel() {
    drawing.value = false
    svgPoints.value = []
  }

  return { drawing, svgPoints, onClick, onContextMenu, cancel }
}
