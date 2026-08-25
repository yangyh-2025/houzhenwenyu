/**
 * Routes: patient area (/) + doctor area (/doctor/*).
 * Doctor auth guard via GET /api/doctor/me (401 -> login).
 */

import { createRouter, createWebHistory } from 'vue-router'
import { request } from '@/api/api.js'

const routes = [
  {
    // 2026-08-24：域名根路径不承载功能、不再跳转——患者端统一使用 /patient
    path: '/',
    name: 'root',
    component: { render: function () { return null } },  // 有意留白（无内容）
  },
  {
    path: '/patient',
    name: 'consent',
    component: () => import('@/views/ConsentView.vue'),
    meta: { area: 'patient' },
  },
  {
    path: '/patient/number',
    name: 'number',
    component: () => import('@/views/NumberEntryView.vue'),
    meta: { area: 'patient' },
  },
  {
    path: '/patient/consult',
    name: 'consult',
    component: () => import('@/views/ConsultView.vue'),
    meta: { area: 'patient' },
  },
  {
    path: '/patient/done',
    name: 'done',
    component: () => import('@/views/DoneView.vue'),
    meta: { area: 'patient' },
  },
  {
    path: '/doctor/login',
    name: 'doctor-login',
    component: () => import('@/views/doctor/LoginView.vue'),
    meta: { area: 'doctor' },
  },
  {
    path: '/doctor',
    name: 'doctor-list',
    component: () => import('@/views/doctor/ListView.vue'),
    meta: { area: 'doctor', auth: true },
  },
  {
    path: '/doctor/records/:id',
    name: 'doctor-detail',
    component: () => import('@/views/doctor/DetailView.vue'),
    meta: { area: 'doctor', auth: true },
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes: routes,
  scrollBehavior(to, from, savedPosition) {
    return savedPosition || { top: 0 }
  },
})

router.beforeEach(async function (to) {
  if (!to.meta.auth) return true
  try {
    await request('/api/doctor/me')
    return true
  } catch (e) {
    return { path: '/doctor/login' }
  }
})
