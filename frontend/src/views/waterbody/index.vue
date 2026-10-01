<template>
  <section class="page" data-module="waterbody">
    <header class="page-head">
      <div>
        <h2>水体养护管理</h2>
        <p class="page-desc">维护水体，围绕水体编号、水体类型、水体面积、水质等级做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记水体</button>
        <button class="btn" type="button" @click="exportRows">导出水体养护清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>水体编号</span>
        <input v-model="keyword" placeholder="按水体编号检索" />
      </label>
      <label class="filter-item">
        <span>水体状态</span>
        <select v-model="status">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">查看详情</button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="busyKey === `${row.id}:${action}`"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无水体养护数据，可先登记水体</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条水体养护记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="noticeMessage" class="success-text">{{ noticeMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>
type ActionResult = { ok: boolean; message: string; entry?: Row }

const ENDPOINT = '/api/waterbody'
const columns = ['水体编号', '水体类型', '水体面积', '水质等级', '富营养化', '换水周期', '管护人员', '水体状态']
const actions = ['记录污染', '净化处理', '验收净化']
const statuses = ['良好', '轻度污染', '重度污染', '净化中', '已净化']

const router = useRouter()
const session = useSessionStore()

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const keyword = ref('')
const status = ref('')
const busyKey = ref('')

const stats = computed(() => {
  const good = rows.value.filter((row) => row['水质等级'] === '良好').length
  const polluted = rows.value.filter((row) => ['轻度污染', '重度污染'].includes(String(row['水质等级']))).length
  const purifying = rows.value.filter((row) => row['水体状态'] === '净化中').length
  return [
    { label: '良好水体', value: good },
    { label: '污染水体', value: polluted },
    { label: '净化中水体', value: purifying },
  ]
})

function resetFilters() {
  keyword.value = ''
  status.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '水体登记入口尚未接入审批流'
}

function openDetail(row: Row) {
  void router.push({ name: 'waterbody-detail', params: { id: row.id } })
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  busyKey.value = `${row.id}:${action}`
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values: { action, version: row.version, operator: session.operator },
      }),
    })
    const payload = (await response.json()) as ActionResult
    if (!response.ok || !payload.ok) {
      if (response.status === 409) {
        errorMessage.value = `${payload.message}，列表已自动刷新为最新数据`
        await reload()
      } else {
        throw new Error(payload.message || '水体养护动作未生效，请稍后重试')
      }
    } else {
      noticeMessage.value = payload.message
      await reload()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '水体养护操作失败'
  } finally {
    busyKey.value = ''
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (status.value) query.set('status', status.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('水体列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '水体养护列表读取失败'
  }
}

onMounted(reload)
</script>
