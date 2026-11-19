import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getNaipStatus } from '../api/client.js'

// NAIP layers (optional naip container, `make naip`), shared by the 2D and the 3D view.
// Five layers, each on/off with a click; RGB and NDVI are the same image floor, so only one
// of the two is on at a time.
export const useNaipStore = defineStore('naip', () => {
  const status = ref({ running: false, model: false, checked: false })
  const layers = ref({ area: true, rgb: true, ndvi: false, ventura: true, truth: true })
  const tile  = ref(null)    // 2D view: response of POST /naip/{sid}/tile
  const patch = ref(null)    // 3D view: response of POST /naip/{sid}/{pid}/patch

  async function checkStatus() {
    try { status.value = { ...(await getNaipStatus()).data, checked: true } }
    catch { status.value = { running: false, model: false, checked: true } }
  }

  function toggle(name) {
    const L = layers.value
    L[name] = !L[name]
    if (name === 'rgb' && L.rgb) L.ndvi = false
    if (name === 'ndvi' && L.ndvi) L.rgb = false
  }

  // True labels exist per image year (2016 / 2018 / 2020): show the year closest to the NAIP image
  function labelYear(result) {
    const ys = [...new Set((result?.truth || []).map(t => t.year).concat((result?.crops || []).map(c => c.year)))]
    if (!ys.length) return null
    const ref_ = result.year ?? Math.max(...ys)
    return ys.reduce((b, y) => (Math.abs(y - ref_) < Math.abs(b - ref_) ? y : b), ys[0])
  }

  return { status, layers, tile, patch, checkStatus, toggle, labelYear }
})
