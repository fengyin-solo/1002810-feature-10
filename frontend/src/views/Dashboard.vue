<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>运营概览</h2>
        <p class="page-desc">汇总各业务模块的关键指标，先看总量再看异常。</p>
      </div>
    </header>
    <div class="stat-row">
      <article v-for="card in cards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>
    <table class="data-table">
      <thead>
        <tr><th>业务模块</th><th>今日新增</th><th>待处理</th><th>异常量</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in moduleRows" :key="row.name">
          <td>{{ row.name }}</td>
          <td>{{ row.created }}</td>
          <td>{{ row.pending }}</td>
          <td>{{ row.abnormal }}</td>
        </tr>
      </tbody>
    </table>

    <section class="water-overview">
      <header class="water-overview-head">
        <h3>水体养护 · 水质等级分布</h3>
        <RouterLink class="link" to="/waterbody">进入水体养护</RouterLink>
      </header>
      <p class="page-desc">与水体列表页、详情页读取同一份数据，保存或净化后此处同步更新。</p>
      <div class="stat-row">
        <article v-for="count in gradeCards" :key="count.label" class="stat-card">
          <span class="stat-label">{{ count.label }}</span>
          <strong class="stat-value">{{ count.value }}</strong>
        </article>
        <article class="stat-card stat-total">
          <span class="stat-label">水体总数</span>
          <strong class="stat-value">{{ waterTotal }}</strong>
        </article>
      </div>
      <p v-if="waterError" class="error-text">{{ waterError }}</p>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { fetchJson } from '@/api/client'
import { QUALITY_GRADES } from '@/views/waterbody/waterbody-shared'

type Overview = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
}

type GradeOverview = {
  total: number
  quality_grades: Record<string, number>
  statuses: Record<string, number>
}

const cards = ref<Overview['cards']>([])
const moduleRows = ref<Overview['modules']>([])
const gradeOverview = ref<GradeOverview | null>(null)
const waterError = ref('')

const gradeCards = computed(() =>
  QUALITY_GRADES.map((grade) => ({
    label: grade,
    value: gradeOverview.value?.quality_grades[grade] ?? 0,
  })),
)
const waterTotal = computed(() => gradeOverview.value?.total ?? 0)

onMounted(async () => {
  try {
    const payload = await fetchJson<Overview>('/api/overview')
    cards.value = payload.cards
    moduleRows.value = payload.modules
  } catch {
    cards.value = [{"label": "业务模块", "value": 0}, {"label": "今日新增", "value": 0}]
    moduleRows.value = [{"name": "绿地台账", "created": 0, "pending": 0, "abnormal": 0}, {"name": "乔木管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "灌木管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "草坪管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "花卉造景", "created": 0, "pending": 0, "abnormal": 0}, {"name": "病虫害防治", "created": 0, "pending": 0, "abnormal": 0}, {"name": "灌溉作业", "created": 0, "pending": 0, "abnormal": 0}, {"name": "施肥作业", "created": 0, "pending": 0, "abnormal": 0}, {"name": "修剪造型", "created": 0, "pending": 0, "abnormal": 0}, {"name": "绿地巡查", "created": 0, "pending": 0, "abnormal": 0}, {"name": "杂草清除", "created": 0, "pending": 0, "abnormal": 0}, {"name": "树木支撑", "created": 0, "pending": 0, "abnormal": 0}, {"name": "苗木移植", "created": 0, "pending": 0, "abnormal": 0}, {"name": "园建设施", "created": 0, "pending": 0, "abnormal": 0}, {"name": "园林机械", "created": 0, "pending": 0, "abnormal": 0}, {"name": "苗木基地", "created": 0, "pending": 0, "abnormal": 0}, {"name": "水体养护", "created": 0, "pending": 0, "abnormal": 0}, {"name": "名木古树", "created": 0, "pending": 0, "abnormal": 0}, {"name": "市民热线", "created": 0, "pending": 0, "abnormal": 0}, {"name": "季度养护方案", "created": 0, "pending": 0, "abnormal": 0}]
  }

  try {
    gradeOverview.value = await fetchJson<GradeOverview>('/api/waterbody/grade-overview')
  } catch {
    waterError.value = '水质等级概览读取失败'
  }
})
</script>

<style scoped>
.water-overview {
  margin-top: 20px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
}
.water-overview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.water-overview-head h3 {
  margin: 0;
  font-size: 15px;
}
.stat-total {
  flex: 0 0 120px;
}
</style>
