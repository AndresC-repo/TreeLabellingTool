import * as THREE from 'three'
import { getPatchPoints } from '../api/client.js'
import { parse3DBuffer } from '../utils/binaryBuffer.js'
import { ref } from 'vue'

export function usePointCloud3D(scene, sessionId, patchId) {
  const loading = ref(false)
  const pointCount = ref(0)
  let pointsMesh = null
  let originalColors = null
  let cachedPositions = null

  async function load() {
    loading.value = true
    try {
      const res = await getPatchPoints(sessionId, patchId)
      const { positions, colors, count } = parse3DBuffer(res.data)
      pointCount.value = count
      originalColors = colors.slice()
      cachedPositions = positions

      if (pointsMesh) { scene.value.remove(pointsMesh); pointsMesh.geometry.dispose(); pointsMesh.material.dispose() }

      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
      geo.setAttribute('color', new THREE.BufferAttribute(colors.slice(), 3))
      const mat = new THREE.PointsMaterial({ size: 2, vertexColors: true, sizeAttenuation: false })
      pointsMesh = new THREE.Points(geo, mat)
      scene.value.add(pointsMesh)

      geo.computeBoundingBox()
      const center = new THREE.Vector3()
      geo.boundingBox.getCenter(center)
      return { center, positions }
    } finally { loading.value = false }
  }

  function highlightIndices(indices, color = [1, 1, 0]) {
    if (!pointsMesh) return
    const colorAttr = pointsMesh.geometry.getAttribute('color')
    const arr = colorAttr.array
    arr.set(originalColors)
    for (const i of indices) { arr[i*3] = color[0]; arr[i*3+1] = color[1]; arr[i*3+2] = color[2] }
    colorAttr.needsUpdate = true
  }

  function applyLabelColor(indices, labelValue) {
    const hue = ((labelValue * 137.5) % 360) / 360
    const [r, g, b] = hslToRgb(hue, 0.7, 0.5)
    if (!pointsMesh) return
    const colorAttr = pointsMesh.geometry.getAttribute('color')
    for (const i of indices) {
      colorAttr.array[i*3] = r; colorAttr.array[i*3+1] = g; colorAttr.array[i*3+2] = b
      originalColors[i*3] = r; originalColors[i*3+1] = g; originalColors[i*3+2] = b
    }
    colorAttr.needsUpdate = true
  }

  function resetColors() {
    if (!pointsMesh || !originalColors) return
    const colorAttr = pointsMesh.geometry.getAttribute('color')
    colorAttr.array.set(originalColors)
    colorAttr.needsUpdate = true
  }

  function getPositions() { return cachedPositions }

  function dispose() {
    if (pointsMesh) {
      scene.value.remove(pointsMesh)
      pointsMesh.geometry.dispose()
      pointsMesh.material.dispose()
      pointsMesh = null
    }
  }

  function hslToRgb(h, s, l) {
    let r, g, b
    if (s === 0) { r = g = b = l } else {
      const q = l < 0.5 ? l*(1+s) : l+s-l*s
      const p = 2*l-q
      r = hue2rgb(p, q, h+1/3); g = hue2rgb(p, q, h); b = hue2rgb(p, q, h-1/3)
    }
    return [r, g, b]
  }
  function hue2rgb(p, q, t) {
    if (t<0) t+=1; if (t>1) t-=1
    if (t<1/6) return p+(q-p)*6*t
    if (t<1/2) return q
    if (t<2/3) return p+(q-p)*(2/3-t)*6
    return p
  }

  return { load, loading, pointCount, highlightIndices, applyLabelColor, resetColors, getPositions, dispose }
}
