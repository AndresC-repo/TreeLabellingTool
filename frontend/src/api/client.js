import axios from 'axios'

const api = axios.create({ baseURL: '/api/v1' })

export const uploadFile = (file, onProgress) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/files/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: e => onProgress && onProgress(Math.round((e.loaded * 100) / e.total)),
  })
}

export const getSessionInfo = sessionId => api.get(`/files/${sessionId}/info`)

export const get2DPoints = (sessionId, scalarField = 'classification', maxPoints = 500000) =>
  api.get(`/view/${sessionId}/points`, {
    params: { scalar_field: scalarField, max_points: maxPoints },
    responseType: 'arraybuffer',
  })

export const get2DImage = (sessionId, scalarField = 'classification', pointSize = 1, width = 2048, height = 2048) =>
  api.get(`/view/${sessionId}/image`, {
    params: { scalar_field: scalarField, point_size: pointSize, width, height },
    responseType: 'blob',
  })

export const extractPatch = (sessionId, payload) =>
  api.post(`/patches/${sessionId}/extract`, payload)

export const getPatchPoints = (sessionId, patchId) =>
  api.get(`/patches/${sessionId}/${patchId}/points`, { responseType: 'arraybuffer' })

export const labelPoints = (sessionId, patchId, payload) =>
  api.post(`/patches/${sessionId}/${patchId}/label`, payload)

export const getNextLabel = (sessionId, patchId) =>
  api.get(`/patches/${sessionId}/${patchId}/next-label`)

export const savePatch = (sessionId, patchId, outputFilename) =>
  api.post(`/patches/${sessionId}/${patchId}/save`, { output_filename: outputFilename })

export const getDownloadUrl = (sessionId, patchId) =>
  `/api/v1/patches/${sessionId}/${patchId}/download`

export const getColormap = (sessionId, scalarField = 'classification') =>
  api.get(`/view/${sessionId}/colormap`, { params: { scalar_field: scalarField } })

export const getPatchColormap = (sessionId, patchId) =>
  api.get(`/patches/${sessionId}/${patchId}/colormap`)

export const predictPatch = (sessionId, patchId, version = 'v1') =>
  api.get(`/patches/${sessionId}/${patchId}/predict`, { params: { version } })

export const applyLabelsBulk = (sessionId, patchId, labels) =>
  api.post(`/patches/${sessionId}/${patchId}/apply-labels-bulk`, { labels })

export const segmentTrees = (sessionId, patchId, labels, params = {}) =>
  api.post(`/patches/${sessionId}/${patchId}/segment-trees`, { labels, ...params })

export const getTreeMetrics = (sessionId, patchId, labels, cell_size, dtmGrid) => {
  const payload = { labels, cell_size }
  if (dtmGrid) {
    payload.dtm_grid   = dtmGrid.grid
    payload.dtm_rows   = dtmGrid.rows
    payload.dtm_cols   = dtmGrid.cols
    payload.dtm_x_min  = dtmGrid.xMin
    payload.dtm_y_min  = dtmGrid.yMin
    payload.dtm_x_range = dtmGrid.xRange
    payload.dtm_y_range = dtmGrid.yRange
  }
  return api.post(`/patches/${sessionId}/${patchId}/tree-metrics`, payload)
}

export const autoTuneSegmentation = (sessionId, patchId, labels, nTrials, dtmGrid) => {
  const payload = { labels, n_trials: nTrials }
  if (dtmGrid) {
    payload.dtm_grid    = dtmGrid.grid
    payload.dtm_rows    = dtmGrid.rows
    payload.dtm_cols    = dtmGrid.cols
    payload.dtm_x_min   = dtmGrid.xMin
    payload.dtm_y_min   = dtmGrid.yMin
    payload.dtm_x_range = dtmGrid.xRange
    payload.dtm_y_range = dtmGrid.yRange
  }
  return api.post(`/patches/${sessionId}/${patchId}/auto-tune-segmentation`, payload)
}

export const markTrainingExample = (sessionId, patchId, semanticLabels, gtInstanceLabels) =>
  api.post(`/patches/${sessionId}/${patchId}/mark-training`, {
    semantic_labels: semanticLabels,
    ...(gtInstanceLabels ? { gt_instance_labels: gtInstanceLabels } : {}),
  })

export const relabelSelection = (sessionId, patchId, pointIndices, fromLabel, toLabel) =>
  api.post(`/patches/${sessionId}/${patchId}/relabel-selection`, {
    point_indices: pointIndices,
    from_label: fromLabel,
    to_label: toLabel,
  })

export const predictInstances = (sessionId, patchId, version = 'v1', params = {}) => {
  const { bandwidth = 2.0, min_points = 100, embed_weight = 0.3, max_spread = 5.0 } = params
  return api.get(`/patches/${sessionId}/${patchId}/predict-instances`, {
    params: { version, bandwidth, min_points, embed_weight, max_spread },
  })
}

export const undoLabel = (sessionId, patchId) =>
  api.post(`/patches/${sessionId}/${patchId}/undo`)

export const restoreFromClient = (sessionId, patchId, buffer) =>
  api.post(`/patches/${sessionId}/${patchId}/restore-from-client`, buffer, {
    headers: { 'Content-Type': 'application/octet-stream' },
    transformRequest: [(data) => data],
  })

export const deletePoints = (sessionId, patchId, pointIndices) =>
  api.post(`/patches/${sessionId}/${patchId}/delete-points`, { point_indices: pointIndices })
