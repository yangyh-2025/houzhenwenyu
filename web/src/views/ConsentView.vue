<template>
  <div class="page">
    <p v-if="lost" class="hint-bar warn lost-notice" role="alert">
      问诊已经中断啦，请重新扫码开始问诊
    </p>

    <h1 class="title">候诊闻语 - 就诊前AI语音采集</h1>

    <div class="card intro">
      <p>本工具用于就诊前收集您身体情况，仅作为医生看病参考，不能替代面诊。</p>
      <p>问诊全程靠「说」和「听」完成：请找一个安静的地方，听完问题后开口回答。</p>
      <p>不需要打字、不需要写姓名，只需按大数字键输入就诊号。</p>
    </div>

    <button type="button" class="btn-big primary" @click="onAgree">同意并继续</button>
    <p class="intro agree-note">点击上面的按钮，就表示您同意使用本语音采集服务。</p>
  </div>
</template>

<script setup>
import { useRoute, useRouter } from 'vue-router'
import { resetConsultation } from '@/store/session.js'

// F1-AC4: every entry resets the checkbox (no persisted consent).
resetConsultation()

var route = useRoute()
var router = useRouter()
var lost = route.query.lost === '1'

// 简化交互（用户需求 2026-08-24）：大按钮即知情同意，点击直接进入下一步
function onAgree() {
  router.push('/patient/number')
}
</script>

<style scoped>
.title {
  font-size: var(--fs-title);
  line-height: 1.35;
  margin: var(--sp-4) 0;
}

.intro p {
  font-size: var(--fs-body);
  line-height: 1.6;
  margin: 0 0 var(--sp-3);
}

.intro p:last-child {
  margin-bottom: 0;
}

.agree-note {
  text-align: center;
  margin-top: var(--sp-3) !important;
}

.lost-notice {
  margin-bottom: var(--sp-4);
}
</style>
