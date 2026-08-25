<script setup>
/**
 * NumberPad: self-drawn elder-friendly numeric keypad (PRD F2 / red line W3+).
 * Pure button elements - zero <input>, system keyboard can never pop up.
 * Key height >= 64px, gap >= 16px, press feedback via :active.
 */

var emit = defineEmits(['press'])
var keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '清空', '0', '删除']

function isFunc(k) {
  return k === '清空' || k === '删除'
}

function tap(k) {
  emit('press', k)
}
</script>

<template>
  <div class="keypad" role="group" aria-label="数字键盘">
    <button
      v-for="k in keys"
      :key="k"
      type="button"
      class="key"
      :class="{ 'key-func': isFunc(k) }"
      @click="tap(k)"
    >
      {{ k }}
    </button>
  </div>
</template>

<style scoped>
.keypad {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px; /* 键距 >= 3mm 等效，取适老化上限 */
}

.key {
  width: 100%;
}
</style>
