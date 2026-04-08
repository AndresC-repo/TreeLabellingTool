import * as THREE from 'three'
import { ref } from 'vue'
import { get2DPoints } from '../api/client.js'
import { parse2DBuffer } from '../utils/binaryBuffer.js'

export function usePointCloud2D(scene, sessionId) {
  const loading = ref(false)
  const pointCount = ref(0)
  const decimationRatio = ref(1)
  let pointsMesh = null

  async function load(scalarField = 'classification') {
    loading.value = true
    try {
      const res = await get2DPoints(sessionId, scalarField)
      const { positions, colors, count } = parse2DBuffer(res.data)
      pointCount.value = count
      decimationRatio.value = parseFloat(res.headers['x-decimation-ratio'] ?? '1')

      if (pointsMesh) {
        scene.value.remove(pointsMesh)
        pointsMesh.geometry.dispose()
        pointsMesh.material.dispose()
        pointsMesh = null
      }

      // Build 3D positions array with z=0 for 2D top-down view
      const pos3 = new Float32Array(count * 3)
      for (let i = 0; i < count; i++) {
        pos3[i * 3]     = positions[i * 2]
        pos3[i * 3 + 1] = positions[i * 2 + 1]
        pos3[i * 3 + 2] = 0
      }

      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.BufferAttribute(pos3, 3))
      geo.setAttribute('color',    new THREE.BufferAttribute(colors, 3))

      const mat = new THREE.PointsMaterial({ size: 1.5, vertexColors: true, sizeAttenuation: false })
      pointsMesh = new THREE.Points(geo, mat)
      scene.value.add(pointsMesh)

      geo.computeBoundingBox()
      const center = new THREE.Vector3()
      geo.boundingBox.getCenter(center)
      return center

    } finally {
      loading.value = false
    }
  }

  function dispose() {
    if (pointsMesh) {
      scene.value?.remove(pointsMesh)
      pointsMesh.geometry.dispose()
      pointsMesh.material.dispose()
      pointsMesh = null
    }
  }

  return { load, loading, pointCount, decimationRatio, dispose }
}
