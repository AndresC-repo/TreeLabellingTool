import axios from 'axios'

const api = axios.create({ baseURL: '/api/v1' })

// The 3D view works in local x/y (relative to the patch origin, see /points). The backend
// works in world coordinates, so a DTM grid is converted on the way out.
export function dtmWorldParams(dtmGrid) {
  return {
    dtm_grid:    Array.from(dtmGrid.grid),
    dtm_rows:    dtmGrid.rows,
    dtm_cols:    dtmGrid.cols,
    dtm_x_min:   dtmGrid.xMin + (dtmGrid.originX ?? 0),
    dtm_y_min:   dtmGrid.yMin + (dtmGrid.originY ?? 0),
    dtm_x_range: dtmGrid.xRange,
    dtm_y_range: dtmGrid.yRange,
  }
}

export const uploadFile = (file, onProgress, folder = null) => {
  const formData = new FormData()
  // pass the bare name: for files picked from a folder, browsers send the folder path in it
  formData.append('file', file, file.name)
  if (folder) formData.append('folder', folder)
  return api.post('/files/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: e => onProgress && onProgress(Math.round((e.loaded * 100) / e.total)),
  })
}

export const getSessionInfo = sessionId => api.get(`/files/${sessionId}/info`)

// units: "m" | "ftUS" | "ft" — overrides the detected linear units of a file
// force: allow units that contradict the file's coordinate system (409 otherwise)
export const setUnits = (sessionId, units, force = false) => api.post(`/files/${sessionId}/units`, { units, force })

export const deleteSession = sessionId => api.delete(`/files/${sessionId}`)

export const get2DPoints = (sessionId, scalarField = 'classification', maxPoints = 500000) =>
  api.get(`/view/${sessionId}/points`, {
    params: { scalar_field: scalarField, max_points: maxPoints },
    responseType: 'arraybuffer',
  })

// view = { xmin, xmax, ymin, ymax } renders only that area at full point density
export const get2DImage = (sessionId, scalarField = 'classification', pointSize = 1, width = 2048, height = 2048, { view, signal } = {}) =>
  api.get(`/view/${sessionId}/image`, {
    params: {
      scalar_field: scalarField, point_size: pointSize, width, height,
      ...(view ? { vx_min: view.xmin, vx_max: view.xmax, vy_min: view.ymin, vy_max: view.ymax } : {}),
    },
    responseType: 'blob',
    signal,
  })

export const getRegions = sessionId => api.get(`/patches/${sessionId}/regions`)

export const deletePatch = (sessionId, patchId) => api.delete(`/patches/${sessionId}/${patchId}`)

export const extractPatch = (sessionId, payload) =>
  api.post(`/patches/${sessionId}/extract`, payload)

export const getPatchPoints = (sessionId, patchId) =>
  api.get(`/patches/${sessionId}/${patchId}/points`, { responseType: 'arraybuffer' })

export const labelPoints = (sessionId, patchId, payload) =>
  api.post(`/patches/${sessionId}/${patchId}/label`, payload)

export const getNextLabel = (sessionId, patchId) =>
  api.get(`/patches/${sessionId}/${patchId}/next-label`)

// outputFilename null/empty = automatic name (<city or state>_<tile>_p<n>_t<trees>.las)
// toLabels: also write into the training labels folder (urban-tree-detection/data/labels)
// confirmUnits: save even if the units checks complain (409 code "units_check" otherwise)
export const savePatch = (sessionId, patchId, outputFilename = null, toLabels = true, confirmUnits = false) =>
  api.post(`/patches/${sessionId}/${patchId}/save`, { output_filename: outputFilename || null, to_labels: toLabels, confirm_units: confirmUnits })

export const getExportName = (sessionId, patchId) =>
  api.get(`/patches/${sessionId}/${patchId}/export-name`)

// ── Dataset overview ──
export const getDataset = () => api.get('/dataset')
export const scanLabelsFolder = () => api.post('/dataset/scan')
export const updateDatasetSource = (name, fields) => api.patch('/dataset/sources', { name, fields })
export const updateDatasetSourcesBulk = (names, fields) => api.patch('/dataset/sources/bulk', { names, fields }).then(r => r.data)
export const locateDatasetSources = (names) => api.post('/dataset/sources/locate', { names }).then(r => r.data)
export const updateDatasetPatch = (key, fields) => api.patch('/dataset/patches', { key, fields })
export const openDatasetPatch = (key) => api.post('/dataset/open', { key })
export const renameDatasetFile = (key, newName) => api.post('/dataset/rename', { key, new_name: newName })
export const datasetCsvUrl = '/api/v1/dataset/patches.csv'

export const getDownloadUrl = (sessionId, patchId) =>
  `/api/v1/patches/${sessionId}/${patchId}/download`

export const getColormap = (sessionId, scalarField = 'classification') =>
  api.get(`/view/${sessionId}/colormap`, { params: { scalar_field: scalarField } })

export const getPatchColormap = (sessionId, patchId) =>
  api.get(`/patches/${sessionId}/${patchId}/colormap`)

// Inference models with their last update on Hugging Face
export const getModels = (refresh = false) => api.get('/models', { params: refresh ? { refresh: 1 } : {} })

export const predictPatch = (sessionId, patchId, version = 'metric', dtmGrid = null) => {
  const payload = { version, ...(dtmGrid ? dtmWorldParams(dtmGrid) : {}) }
  return api.post(`/patches/${sessionId}/${patchId}/predict`, payload)
}

export const applyLabelsBulk = (sessionId, patchId, labels) =>
  api.post(`/patches/${sessionId}/${patchId}/apply-labels-bulk`, { labels })

export const segmentTrees = (sessionId, patchId, labels, params = {}) =>
  api.post(`/patches/${sessionId}/${patchId}/segment-trees`, { labels, ...params })

export const getTreeMetrics = (sessionId, patchId, labels, cell_size, dtmGrid) => {
  const payload = { labels, cell_size, ...(dtmGrid ? dtmWorldParams(dtmGrid) : {}) }
  return api.post(`/patches/${sessionId}/${patchId}/tree-metrics`, payload)
}

export const relabelSelection = (sessionId, patchId, pointIndices, fromLabel, toLabel) =>
  api.post(`/patches/${sessionId}/${patchId}/relabel-selection`, {
    point_indices: pointIndices,
    from_label: fromLabel,
    to_label: toLabel,
  })

export const predictInstances = (sessionId, patchId, version = 'metric_old', params = {}, threshold = null) => {
  const { bandwidth = 2.0, min_points = 100, embed_weight = 0.3, max_spread = 5.0 } = params
  return api.get(`/patches/${sessionId}/${patchId}/predict-instances`, {
    params: { version, bandwidth, min_points, embed_weight, max_spread, ...(threshold != null ? { threshold } : {}) },
  })
}

export const redoLabel = (sessionId, patchId) =>
  api.post(`/patches/${sessionId}/${patchId}/redo`)

export const getLabelHistory = (sessionId, patchId) =>
  api.get(`/patches/${sessionId}/${patchId}/history`)

export const undoLabel = (sessionId, patchId) =>
  api.post(`/patches/${sessionId}/${patchId}/undo`)

// buffer holds local x/y; origin ({x, y}) turns them back into world coordinates
export const restoreFromClient = (sessionId, patchId, buffer, origin = { x: 0, y: 0 }) =>
  api.post(`/patches/${sessionId}/${patchId}/restore-from-client`, buffer, {
    params: { origin_x: origin.x, origin_y: origin.y },
    headers: { 'Content-Type': 'application/octet-stream' },
    transformRequest: [(data) => data],
  })

export const deletePoints = (sessionId, patchId, pointIndices) =>
  api.post(`/patches/${sessionId}/${patchId}/delete-points`, { point_indices: pointIndices })

// load=false: ZIP of the tiles (blob). load=true: tiles loaded into the tool as a folder
// → { folder, tiles: [upload responses] }
export const splitFile = (file, nTiles, onProgress, load = false) => {
  const formData = new FormData()
  formData.append('file', file, file.name)
  formData.append('n_tiles', nTiles)
  formData.append('load', load ? 'true' : 'false')
  return api.post('/files/split', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    responseType: load ? 'json' : 'blob',
    onUploadProgress: e => onProgress && onProgress(Math.round((e.loaded * 100) / e.total)),
  })
}
