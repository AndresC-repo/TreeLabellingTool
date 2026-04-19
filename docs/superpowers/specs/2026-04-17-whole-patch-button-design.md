# Whole Patch Button — Design Spec

**Date:** 2026-04-17  
**Status:** Approved

## Summary

Add a "Whole Patch" button to the 2D view that loads the entire LAS file into the point cloud view without requiring a rectangle or polygon selection. When the resulting patch is saved, the output filename defaults to the original LAS filename (no `_patch_N` suffix).

## Approach

Frontend-only. The button uses the full dataset bounding box already available in the session info and calls the existing `POST /extract` endpoint with `selection_type: "rectangle"`. No backend changes are needed.

The "whole patch" state is communicated to the 3D view via a `?whole=1` URL query parameter, which the 3D view stores in Pinia and SavePanel reads to adjust the default filename.

## Components Changed

### 1. `frontend/src/views/View2D.vue`
- Add a "Whole Patch" button in the toolbar alongside the existing selection tools.
- On click: call `extractPatch(sessionId, { selection_type: 'rectangle', bounds_2d: fullBounds })` where `fullBounds` is the full x/y extent of the loaded dataset (already available from the session info or the canvas renderer's world bounds).
- On success: navigate to `/session/:id/patch/:patchId?n=N&whole=1`.

### 2. `frontend/src/views/PatchView3D.vue`
- On mount, check `route.query.whole === '1'` and set `store.isWholePatch = true`.

### 3. `frontend/src/stores/patch3d.js`
- Add `isWholePatch: ref(false)`.
- Clear it in `reset()`.
- Export it from the store.

### 4. `frontend/src/components/patch3d/SavePanel.vue`
- If `store.isWholePatch`, default filename = `{stem}.las` (original filename, no `_patch_N` or label suffix).
- User can still edit the filename before saving.

## Data Flow

```
User clicks "Whole Patch"
  → extractPatch({ selection_type: 'rectangle', bounds_2d: fullBounds })
  → backend returns { patch_id, patch_number, point_count, ... }
  → router.push(`/session/:id/patch/:patchId?n=N&whole=1`)
  → PatchView3D mounts → store.isWholePatch = true
  → SavePanel suggests "{stem}.las" instead of "{stem}_patch_N.las"
```

## Edge Cases

| Scenario | Behaviour |
|----------|-----------|
| Very large file | Loads fully — no confirmation (user-confirmed preference). Performance is the same as any large rectangle selection. |
| User edits filename | SavePanel input is always editable; the default is just a suggestion. |
| User extracts a normal rectangle after Whole Patch | `store.reset()` clears `isWholePatch`; normal filename logic applies. |
| `whole=1` missing from URL (direct navigation) | `isWholePatch` stays false; standard filename behaviour. |

## What Does NOT Change

- Backend extraction logic — no new endpoint or selection type needed.
- The patch is stored and labelled identically to any other patch.
- "Apply to Labels" and segmentation features work unchanged.
