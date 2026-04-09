import { ref } from 'vue'

/**
 * Freehand polygon selection tool.
 * Left-click adds points; right-click closes the polygon.
 * @param {Function} toWorld — (clientX, clientY) => { x, y }
 * @param {import('vue').Ref} domEl — ref to the canvas element
 */
export function useSelectionFreehand(toWorld, domEl) {
  const drawing = ref(false)
  const svgPoints = ref([])

  function onClick(e) {
    if (e.button !== 0) return
    drawing.value = true
    svgPoints.value.push({ x: e.offsetX, y: e.offsetY })
  }

  function onContextMenu(e) {
    e.preventDefault()
    if (!drawing.value || svgPoints.value.length < 3) {
      svgPoints.value = []; drawing.value = false; return null
    }
    drawing.value = false
    const el = domEl.value
    const r = el.getBoundingClientRect()
    const worldPoly = svgPoints.value.map(p => {
      const w = toWorld(p.x + r.left, p.y + r.top)
      return [w.x, w.y]
    })
    svgPoints.value = []
    return worldPoly
  }

  function cancel() { drawing.value = false; svgPoints.value = [] }

  return { drawing, svgPoints, onClick, onContextMenu, cancel }
}
