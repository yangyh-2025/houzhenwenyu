<template>
  <div class="page done-page">
    <div class="done-icon" aria-hidden="true">
      <span class="check">✓</span>
    </div>

    <h1 class="done-title">提交成功，请等待面诊。</h1>
    <p class="done-note">
      您的身体情况已经交给医生，请安心等候叫号。
    </p>
    <p class="done-sub">
      摘要仅供医生面诊参考，最终以医生当面诊断为准。
    </p>
  </div>
</template>

<style scoped>
.done-icon {
  width: 96px;
  height: 96px;
  border-radius: 50%;
  background: var(--c-primary-light);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: var(--sp-6) auto var(--sp-5);
}

.done-icon .check {
  font-size: 56px;
  font-weight: 700;
  color: var(--c-primary);
}

.done-title {
  font-size: var(--fs-huge);
  line-height: 1.3;
  text-align: center;
  margin: 0 0 var(--sp-4);
}

.done-note {
  font-size: var(--fs-big);
  text-align: center;
  color: var(--c-text);
  margin: 0 0 var(--sp-3);
}

.done-sub {
  font-size: var(--fs-body);
  text-align: center;
  color: var(--c-muted);
}
</style>
