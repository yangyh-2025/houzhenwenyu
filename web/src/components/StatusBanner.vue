<template>
  <div class="status-banner" :class="tone" role="status">
    <span class="dot" aria-hidden="true"></span>
    <span class="txt">{{ text }}</span>
  </div>
  <p v-if="subText" class="sub">{{ subText }}</p>
</template>

<script setup>
/**
 * StatusBanner: three-state big-text status strip (PRD F3-R3):
 * playing=正在提问 / listening=请您回答 / processing=AI正在思考，请稍候。
 */
defineProps({
  tone: { type: String, default: 'info' },
  text: { type: String, required: true },
  subText: { type: String, default: '' },
})
</script>

<style scoped>
.status-banner {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  min-height: 64px;
  padding: 12px 16px;
  border-radius: 12px;
  font-size: var(--fs-big);
  font-weight: 700;
}

.status-banner .dot {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  flex: none;
}

.status-banner .txt {
  flex: 1;
}

.status-banner.playing {
  background: var(--c-primary-light);
  color: var(--c-primary-dark);
}
.status-banner.playing .dot {
  background: var(--c-primary);
}

.status-banner.listening {
  background: var(--c-warn-bg);
  color: var(--c-warn);
}
.status-banner.listening .dot {
  background: var(--c-warn);
  animation: pulse 1.1s ease-in-out infinite;
}

.status-banner.processing {
  background: var(--c-info-bg);
  color: var(--c-info);
}
.status-banner.processing .dot {
  animation: pulse 1.1s ease-in-out infinite;
  background: var(--c-info);
}

@keyframes pulse {
  0% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.35; transform: scale(0.8); }
  100% { opacity: 1; transform: scale(1); }
}

.sub {
  font-size: var(--fs-body);
  color: var(--c-warn);
  font-weight: 700;
  margin: var(--sp-3) 0 0;
}
</style>
