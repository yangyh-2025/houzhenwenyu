<template>
  <div class="page-doctor login-page">
    <h1 class="login-title">候诊闻语 · 医生后台</h1>

    <form class="login-form" @submit.prevent="onSubmit">
      <label class="field">
        <span class="field-label">账号</span>
        <input
          v-model="username"
          type="text"
          name="username"
          autocomplete="username"
          autocapitalize="off"
          required
        />
      </label>

      <label class="field">
        <span class="field-label">密码</span>
        <input
          v-model="password"
          type="password"
          name="password"
          autocomplete="current-password"
          required
        />
      </label>

      <p v-if="error" class="hint-bar error" role="alert">{{ error }}</p>

      <button type="submit" class="btn-big primary" :disabled="busy">登录</button>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { request } from '@/api/api.js'

var router = useRouter()
var username = ref('')
var password = ref('')
var error = ref('')
var busy = ref(false)

function onSubmit() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  request('/api/doctor/login', {
    method: 'POST',
    body: { username: username.value, password: password.value },
  })
    .then(function () {
      router.replace('/doctor')
    })
    .catch(function (e) {
      error.value = e.message || '登录没有成功，请重试'
    })
    .finally(function () {
      busy.value = false
    })
}
</script>

<style scoped>
.login-title {
  font-size: var(--fs-title);
  margin: var(--sp-6) 0 var(--sp-5);
}

.field {
  display: block;
  margin-bottom: var(--sp-4);
}

.field-label {
  display: block;
  font-size: var(--fs-body);
  font-weight: 700;
  margin-bottom: var(--sp-2);
}

input {
  width: 100%;
  min-height: 52px;
  font-size: var(--fs-body);
  padding: 10px 14px;
  border: 2px solid var(--c-border);
  border-radius: 12px;
}

input:focus {
  outline: 3px solid var(--c-primary-light);
  border-color: var(--c-primary);
}
</style>
