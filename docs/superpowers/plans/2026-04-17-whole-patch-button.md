# Whole Patch Button — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Whole Patch" button to the 2D toolbar that loads the entire LAS file into the 3D patch view, and defaults the save filename to the original LAS filename (no `_patch_N` suffix).

**Architecture:** The button calls the existing `POST /extract` endpoint with the full dataset bounding box (already in `session.bounds`). A `?whole=1` query param is appended to the navigation URL; `PatchView3D` reads it on mount and sets `store.isWholePatch = true`; `SavePanel` checks that flag to adjust the suggested filename.

**Tech Stack:** Vue 3 (Composition API), Pinia, Vue Router, existing FastAPI backend (no backend changes).

---

### Task 1: Add `isWholePatch` to the patch3d store

**Files:**
- Modify: `frontend/src/stores/patch3d.js`

- [ ] **Step 1: Add the ref and wire it into reset() and the return object**

Open `frontend/src/stores/patch3d.js`. Make three edits:

*After the line `const segmenting = ref(false)` (around line 23), add:*
```js
const isWholePatch = ref(false)
```

*Inside `reset()`, after `segmenting.value = false`, add:*
```js
isWholePatch.value = false
```

*In the `return { ... }` object, add `isWholePatch` alongside the other exports.*

- [ ] **Step 2: Verify by inspection**

Open `frontend/src/stores/patch3d.js` and confirm:
- `const isWholePatch = ref(false)` exists
- `isWholePatch.value = false` is inside `reset()`
- `isWholePatch` is in the return object

- [ ] **Step 3: Commit**
```bash
git add frontend/src/stores/patch3d.js
git commit -m "feat: add isWholePatch ref to patch3d store"
```

---

### Task 2: Read `?whole=1` in PatchView3D and set store flag

**Files:**
- Modify: `frontend/src/views/PatchView3D.vue:101-104`

- [ ] **Step 1: Update the onMounted block**

In `frontend/src/views/PatchView3D.vue`, replace the `onMounted` block:

```js
onMounted(() => {
  store.patchNumber = parseInt(route.query.n) || 1
  document.addEventListener('keydown', onKeyDown)
})
```

with:

```js
onMounted(() => {
  store.patchNumber = parseInt(route.query.n) || 1
  store.isWholePatch = route.query.whole === '1'
  document.addEventListener('keydown', onKeyDown)
})
```

- [ ] **Step 2: Commit**
```bash
git add frontend/src/views/PatchView3D.vue
git commit -m "feat: set isWholePatch from URL query param in PatchView3D"
```

---

### Task 3: Update SavePanel to use original filename when isWholePatch

**Files:**
- Modify: `frontend/src/components/patch3d/SavePanel.vue:31-37`

- [ ] **Step 1: Update the suggestedFilename computed**

In `frontend/src/components/patch3d/SavePanel.vue`, replace the `suggestedFilename` computed:

```js
const suggestedFilename = computed(() => {
  const stem = (session.filename ?? 'output').replace(/\.la[sz]$/i, '')
  const n = patchStore.patchNumber
  const labels = patchStore.appliedLabels
  if (labels.length === 0) return `${stem}_patch_${n}.las`
  return `${stem}_patch_${n}_${labels.join('_')}.las`
})
```

with:

```js
const suggestedFilename = computed(() => {
  const stem = (session.filename ?? 'output').replace(/\.la[sz]$/i, '')
  if (patchStore.isWholePatch) return `${stem}.las`
  const n = patchStore.patchNumber
  const labels = patchStore.appliedLabels
  if (labels.length === 0) return `${stem}_patch_${n}.las`
  return `${stem}_patch_${n}_${labels.join('_')}.las`
})
```

- [ ] **Step 2: Verify by inspection**

Confirm the `if (patchStore.isWholePatch)` branch returns `${stem}.las` before the patch-number logic.

- [ ] **Step 3: Commit**
```bash
git add frontend/src/components/patch3d/SavePanel.vue
git commit -m "feat: use original filename in SavePanel when isWholePatch"
```

---

### Task 4: Add "Whole Patch" button to the 2D toolbar

**Files:**
- Modify: `frontend/src/views/View2D.vue`

This task adds the button, the `extractPatch` API import, a loading ref, and the `loadWholePatch` handler.

- [ ] **Step 1: Add `extractPatch` to the import and add the loading ref**

In `frontend/src/views/View2D.vue`, update the `client.js` import line:

```js
import { uploadFile, extractPatch } from '../api/client.js'
```

Add a loading ref alongside the existing refs (after `const dropdownOpen = ref(false)`):

```js
const extractingWhole = ref(false)
```

- [ ] **Step 2: Add the `loadWholePatch` function**

Add this function after the `openPatch` function:

```js
async function loadWholePatch() {
  const sessionId = route.params.id
  const entry = session.sessions.find(s => s.sessionId === sessionId)
  if (!entry?.bounds) return
  extractingWhole.value = true
  try {
    const bounds = entry.bounds
    const res = await extractPatch(sessionId, {
      selection_type: 'rectangle',
      bounds_2d: {
        x_min: bounds.x[0],
        x_max: bounds.x[1],
        y_min: bounds.y[0],
        y_max: bounds.y[1],
      },
    })
    const { patch_id, patch_number } = res.data
    router.push(`/session/${sessionId}/patch/${patch_id}?n=${patch_number}&whole=1`)
  } catch (err) {
    console.error('Whole patch extraction failed:', err)
  } finally {
    extractingWhole.value = false
  }
}
```

- [ ] **Step 3: Add the button to the toolbar template**

In the toolbar, add the "Whole Patch" button inside the `.tool-group` div, after the existing tool buttons loop:

```html
<div class="tool-group">
  <button
    v-for="tool in tools"
    :key="tool.id"
    :class="{ active: store.activeTool === tool.id }"
    @click="store.activeTool = tool.id"
  >{{ tool.label }}</button>
  <button
    class="whole-btn"
    :disabled="extractingWhole"
    @click="loadWholePatch"
    title="Load the entire LAS file into the point cloud view"
  >{{ extractingWhole ? 'Loading…' : 'Whole Patch' }}</button>
</div>
```

- [ ] **Step 4: Add the button style**

In the `<style scoped>` block, add after `.tool-group`:

```css
.whole-btn {
  background: #2a3a5e;
  border-color: #4a6aae;
  color: #adf;
}
.whole-btn:hover:not(:disabled) { background: #3a4a7e; }
```

- [ ] **Step 5: Commit**
```bash
git add frontend/src/views/View2D.vue
git commit -m "feat: add Whole Patch button to 2D toolbar"
```

---

### Task 5: Manual smoke test

- [ ] Open the app in the browser and load a LAS file.
- [ ] Confirm the "Whole Patch" button appears in the toolbar to the right of "Fixed Rect".
- [ ] Click "Whole Patch" — button should show "Loading…" then navigate to the 3D view.
- [ ] Confirm all points of the file are visible in the 3D view.
- [ ] Open the Save panel — filename should be `{original_stem}.las` (no `_patch_N`).
- [ ] Edit the filename and save — confirm download works.
- [ ] Navigate back, draw a normal rectangle selection, open it — confirm SavePanel filename reverts to `{stem}_patch_N.las` pattern (isWholePatch is false for normal patches).
