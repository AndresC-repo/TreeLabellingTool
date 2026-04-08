import { CLASSIFICATION_COLORS } from '../utils/colorMaps.js'

/**
 * Convert a classification code to a CSS hex color string.
 * Falls back to grey for unrecognized codes.
 */
export function classCodeToHex(code) {
  return CLASSIFICATION_COLORS[code] ?? '#999999'
}

/**
 * Convert a normalized float (0-1) intensity value to a greyscale CSS hex string.
 */
export function intensityToHex(normalizedValue) {
  const v = Math.round(Math.max(0, Math.min(1, normalizedValue)) * 255)
  const hex = v.toString(16).padStart(2, '0')
  return `#${hex}${hex}${hex}`
}

/**
 * Map a number_of_returns value (1-7) to a CSS hex color (red → green gradient).
 */
export function returnsToHex(value) {
  const t = Math.max(0, Math.min(1, (value - 1) / 6))
  const r = Math.round(t * 255)
  const g = Math.round((1 - t) * 255)
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}00`
}
