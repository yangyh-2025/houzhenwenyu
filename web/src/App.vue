<script setup>
/**
 * App shell: F5 banner above patient routes; keep-alive only for
 * the doctor list so returning from detail preserves browse position (F8-AC3).
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import IosBanner from '@/components/IosBanner.vue'
import { needsSafariGuide } from '@/lib/env.js'

var route = useRoute()
var showBanner = computed(function () {
  return route.meta.area === 'patient' && needsSafariGuide
})
</script>

<template>
  <IosBanner v-if="showBanner" />
  <router-view v-slot="{ Component }">
    <keep-alive include="DoctorListView">
      <component :is="Component" />
    </keep-alive>
  </router-view>
</template>
