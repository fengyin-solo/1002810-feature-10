<template>
  <section class="page" data-module="waterbody-detail">
    <header class="page-head">
      <div>
        <h2>水体养护详情</h2>
        <p class="page-desc">
          <RouterLink class="link" :to="{ name: 'waterbody' }">返回水体列表</RouterLink>
          ｜ 保存后请刷新页面核对：列表页与本详情页读的是同一份数据。
        </p>
      </div>
    </header>

    <div v-if="notFound" class="detail-card">
      <p class="error-text">{{ errorMessage || '水体不存在或已归档' }}</p>
    </div>

    <template v-else-if="entry">
      <div class="detail-grid">
        <article class="detail-card">
          <h3>基础信息</h3>
          <dl class="detail-dl">
            <div v-for="field in readonlyFields" :key="field">
              <dt>{{ field }}</dt>
              <dd>{{ entry[field] ?? '—' }}</dd>
            </div>
            <div>
              <dt>当前版本</dt>
              <dd>v{{ entry.version }}</dd>
            </div>
          </dl>
        </article>

        <article class="detail-card">
          <h3>保存水质登记结果</h3>
          <form class="detail-form" @submit.prevent="save">
            <label class="form-item">
              <span>水质等级</span>
              <select v-model="form.水质等级">
                <option v-for="grade in grades" :key="grade" :value="grade">{{ grade }}</option>
              </select>
            </label>
            <label class="form-item">
              <span>富营养化程度</span>
              <select v-model="form.富营养化">
                <option v-for="level in eutroLevels" :key="level" :value="level">{{ level }}</option>
              </select>
            </label>
            <label class="form-item">
              <span>换水周期</span>
              <input v-model="form.换水周期" placeholder="例如：每15天" />
            </label>
            <label class="form-item">
              <span>管护人员</span>
              <input v-model="form.管护人员" placeholder="填写本次管护人员" />
            </label>
            <label class="form-item form-item-full">
              <span>
                变更原因<em v-if="gradeChanging" class="required">（水质等级发生变更，必填）</em>
              </span>
              <textarea
                v-model="reason"
                rows="3"
                :placeholder="gradeChanging
                  ? '水质等级只能逐级变更，请说明本次由「' + entry['水质等级'] + '」变为「' + form.水质等级 + '」的原因'
                  : '未变更水质等级时可不填'"
              ></textarea>
            </label>
            <div class="form-item form-item-full form-actions">
              <button class="btn primary" type="submit" :disabled="saving">
                {{ saving ? '保存中…' : `保存（基于 v${entry.version}）` }}
              </button>
              <button class="btn ghost" type="button" :disabled="saving" @click="resetForm">
                还原为当前值
              </button>
            </div>
          </form>
          <p v-if="gradeChanging" class="hint-text">
            当前「{{ entry['水质等级'] }}」→ 新值「{{ form.水质等级 }}」为相邻级别，允许保存；
            系统拒绝跨级（如良好直接改重度污染）。
          </p>
        </article>
      </div>

      <article class="detail-card">
        <h3>养护动作</h3>
        <p class="hint-text">动作与保存共用版本号：两人前后脚操作时，后到的一次会被拒绝并提示该水体已被占用。</p>
        <div class="row-actions">
          <button
            v-for="action in actions"
            :key="action"
            class="btn"
            type="button"
            :disabled="runningAction !== ''"
            @click="runAction(action)"
          >
            {{ runningAction === action ? '执行中…' : action }}
          </button>
        </div>
      </article>

      <article class="detail-card">
        <h3>变更留痕</h3>
        <table class="data-table">
          <thead>
            <tr>
              <th v-for="column in historyColumns" :key="column">{{ column }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in history" :key="index">
              <td v-for="column in historyColumns" :key="column">{{ item[column] ?? '—' }}</td>
            </tr>
            <tr v-if="!history.length">
              <td :colspan="historyColumns.length" class="empty-state">暂无变更记录</td>
            </tr>
          </tbody>
        </table>
      </article>
    </template>

    <footer class="page-foot">
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="noticeMessage" class="success-text">{{ noticeMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Entry = {
  id: number
  version: number
  history: HistoryItem[]
  [key: string]: string | number | HistoryItem[] | null
}
type HistoryItem = Record<string, string>
type ActionResult = { ok: boolean; message: string; entry?: Entry }

const ENDPOINT = '/api/waterbody'
const readonlyFields = ['水体编号', '水体类型', '水体面积', '水质等级', '富营养化', '换水周期', '管护人员', '水体状态']
const grades = ['良好', '轻度污染', '重度污染']
const eutroLevels = ['无', '轻度', '中度', '重度']
const actions = ['记录污染', '净化处理', '验收净化']
const historyColumns = ['时间', '操作人', '动作', '由', '至', '原因']

const route = useRoute()
const session = useSessionStore()

const entry = ref<Entry | null>(null)
const notFound = ref(false)
const errorMessage = ref('')
const noticeMessage = ref('')
const saving = ref(false)
const runningAction = ref('')
const reason = ref('')

const form = reactive({
  水质等级: '良好',
  富营养化: '无',
  换水周期: '',
  管护人员: '',
})

const history = computed<HistoryItem[]>(() => entry.value?.history ?? [])
const gradeChanging = computed(() => !!entry.value && form.水质等级 !== String(entry.value['水质等级'] ?? ''))

function applyForm(current: Entry) {
  form.水质等级 = String(current['水质等级'] ?? '良好')
  form.富营养化 = String(current['富营养化'] ?? '无')
  form.换水周期 = String(current['换水周期'] ?? '')
  form.管护人员 = String(current['管护人员'] ?? '')
}

function resetForm() {
  if (entry.value) applyForm(entry.value)
  reason.value = ''
  errorMessage.value = ''
}

async function loadEntry(isRetry = false) {
  const id = route.params.id
  try {
    const response = await request(`${ENDPOINT}/${id}`)
    if (response.status === 404) {
      notFound.value = true
      return
    }
    if (!response.ok) {
      throw new Error('水体详情读取失败')
    }
    const payload = (await response.json()) as Entry
    entry.value = payload
    notFound.value = false
    if (!isRetry) {
      applyForm(payload)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '水体详情读取失败'
  }
}

async function save() {
  if (!entry.value) return
  errorMessage.value = ''
  noticeMessage.value = ''
  saving.value = true
  try {
    const response = await request(`${ENDPOINT}/${entry.value.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        values: { ...form, version: entry.value.version, operator: session.operator },
        remark: reason.value,
      }),
    })
    const payload = (await response.json()) as ActionResult
    if (!response.ok || !payload.ok || !payload.entry) {
      if (response.status === 409 && payload.entry) {
        entry.value = payload.entry
        applyForm(payload.entry)
        reason.value = ''
        errorMessage.value = `${payload.message}，本页已载入最新版本，请核对后再保存`
      } else {
        throw new Error(payload.message || '保存失败，请稍后重试')
      }
    } else {
      entry.value = payload.entry
      applyForm(payload.entry)
      reason.value = ''
      noticeMessage.value = payload.message
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '保存失败，请稍后重试'
  } finally {
    saving.value = false
  }
}

async function runAction(action: string) {
  if (!entry.value) return
  errorMessage.value = ''
  noticeMessage.value = ''
  runningAction.value = action
  try {
    const response = await request(`${ENDPOINT}/${entry.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values: { action, version: entry.value.version, operator: session.operator },
        remark: reason.value || undefined,
      }),
    })
    const payload = (await response.json()) as ActionResult
    if (!response.ok || !payload.ok || !payload.entry) {
      if (response.status === 409 && payload.entry) {
        entry.value = payload.entry
        applyForm(payload.entry)
        reason.value = ''
        errorMessage.value = `${payload.message}，本页已载入最新版本，请核对后再操作`
      } else {
        throw new Error(payload.message || '动作执行失败，请稍后重试')
      }
    } else {
      entry.value = payload.entry
      applyForm(payload.entry)
      reason.value = ''
      noticeMessage.value = payload.message
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '动作执行失败'
  } finally {
    runningAction.value = ''
  }
}

onMounted(() => void loadEntry())
</script>
