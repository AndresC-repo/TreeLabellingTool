<template>
  <label class="scalar-selector">
    <span>Color by:</span>
    <select v-model="store.scalarField">
      <option value="elevation">Elevation (Z)</option>
      <option value="classification">Classification</option>
      <option value="intensity">Intensity</option>
      <option value="number_of_returns">Number of Returns</option>
    </select>
  </label>
</template>

<script setup>
import { useView2DStore } from '../../stores/view2d.js'
const store = useView2DStore()
</script>

<style scoped>
.scalar-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #aac;
}
select {
  background: #2a2a4e;
  color: #eee;
  border: 1px solid #556;
  padding: 5px 10px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}
select:focus { outline: 2px solid #7ab3ff; }
</style>
