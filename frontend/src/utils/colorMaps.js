// ASPRS classification code → hex color (mirrors backend projection.py)
export const CLASSIFICATION_COLORS = {
  0:  '#808080', 1:  '#b3b3b3', 2:  '#8B4513',
  3:  '#228B22', 4:  '#00cc00', 5:  '#006400',
  6:  '#ff0000', 7:  '#ff8000', 9:  '#0080ff',
  17: '#ccccff', 18: '#ff00ff',
}

export function classificationColor(value) {
  return CLASSIFICATION_COLORS[value] ?? '#999999'
}
