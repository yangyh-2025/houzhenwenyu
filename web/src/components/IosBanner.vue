<script setup>
/**
 * IosBanner: F5 persistent guidance banner.
 * Shown on every patient page while the user stays in iOS WeChat
 * in-app browser, or when mediaDevices is unavailable (fallback).
 */
import { needsSafariGuide } from '@/lib/env.js'
</script>

<template>
  <div v-if="needsSafariGuide" class="ios-banner" role="alert">
    <span class="warn-mark">⚠️</span>
    <span>苹果手机请点右上角「…」选择在 Safari 中打开网页，再进行语音问诊。</span>
  </div>
</template>

<style scoped>
.ios-banner {
  position: sticky;
  top: 0;
  z-index: 50;
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 14px 16px;
  background: #fff7ed;
  border-bottom: 3px solid var(--c-warn);
}

.warn-mark {
  font-size: var(--fs-big);
  line-height: 1.2;
}

.ios-banner span:last-child {
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--c-warn);
  line-height: 1.4;
}
</style>
