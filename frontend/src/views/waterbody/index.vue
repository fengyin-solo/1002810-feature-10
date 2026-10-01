<template>
  <section class="page" data-module="waterbody">
    <header class="page-head">
      <div>
        <h2>水体养护管理</h2>
        <p class="page-desc">
          维护水体编号、类型、面积、水质等级、富营养化与状态；保存后列表、详情与工作台读到的是同一份最新数据。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="showCreate = true">登记水体</button>
        <button class="btn" type="button" @click="exportRows">导出水体养护清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in gradeStats" :key="item.label" class="stat-card">
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
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="state in STATUSES" :key="state" :value="state">{{ state }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in COLUMNS" :key="column">{{ column }}</th>
          <th>可执行动作</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in COLUMNS" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in ACTION_LABELS"
              :key="action"
              class="link"
              type="button"
              :disabled="!canRun(action, row)"
              :title="canRun(action, row) ? action : `当前为「${row['水体状态']}」，不可执行${action}`"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
          <td>
            <RouterLink class="link" :to="`/waterbody/${row.id}`">明细 / 保存</RouterLink>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="COLUMNS.length + 2" class="empty-state">暂无水体养护数据，可先登记水体</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条水体养护记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <form class="modal-card" @submit.prevent="createRow">
        <h3>登记水体</h3>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <label v-for="field in createFields" :key="field" class="filter-item">
          <span>{{ field }}</span>
          <input v-model="createForm[field]" :placeholder="`请输入${field}`" />
        </label>
        <div class="modal-actions">
          <button class="btn primary" type="submit">登记</button>
          <button class="btn ghost" type="button" @click="showCreate = false">取消</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import {
  ACTION_ALLOWED_FROM,
  ACTION_LABELS,
  COLUMNS,
  ENDPOINT,
  QUALITY_GRADES,
  STATUSES,
  pickError,
  type WaterbodyRow,
} from './waterbody-shared'

const rows = ref<WaterbodyRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')

const showCreate = ref(false)
const createError = ref('')
const createFields = ['水体编号', '水体类型', '水体面积', '换水周期', '管护人员']
const createForm = reactive<Record<string, string>>({})

const gradeStats = computed(() =>
  QUALITY_GRADES.map((grade) => ({
    label: grade,
    value: rows.value.filter((row) => row['水质等级'] === grade).length,
  })),
)

function canRun(action: string, row: WaterbodyRow): boolean {
  return ACTION_ALLOWED_FROM[action]?.includes(row['水体状态']) ?? false
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function createRow() {
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm } }),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok || payload.ok === false) {
      createError.value = payload.detail ?? payload.message ?? '登记失败，请检查必填项'
      return
    }
    showCreate.value = false
    createFields.forEach((field) => {
      createForm[field] = ''
    })
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '登记失败'
  }
}

async function runAction(action: string, row: WaterbodyRow) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      // 携带进入列表时读到的版本：若期间被他人保存/操作，后到一次会被 409 拒绝。
      body: JSON.stringify({ action, expected_version: row.version }),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(payload.detail ?? '该水体已被占用，动作未生效，请刷新后再试')
    }
    if (payload.ok === false) {
      throw new Error(payload.message ?? '动作未生效')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '水体养护操作失败'
    await reload()
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (statusFilter.value) query.set('status', statusFilter.value)
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

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-card {
  width: 420px;
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.modal-card h3 {
  margin: 0;
}
.modal-card .filter-item span {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.modal-card input {
  width: 100%;
  padding: 7px 9px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 6px;
}
.link:disabled {
  color: #9aa6b2;
  cursor: not-allowed;
}
</style>
