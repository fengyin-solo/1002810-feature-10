<template>
  <section class="page" data-module="waterbody-detail">
    <header class="page-head">
      <div>
        <h2>水体明细 · {{ entry?.['水体编号'] ?? '载入中' }}</h2>
        <p class="page-desc">
          详情页与列表页、工作台读取同一份数据；保存带版本校验，水质等级每次只能调整一级且需填写原因。
        </p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/waterbody">返回列表</RouterLink>
      </div>
    </header>

    <p v-if="loadError" class="error-text">{{ loadError }}</p>

    <template v-else-if="entry">
      <div class="meta-strip">
        <span class="meta-tag">数据版本 v{{ form.version }}</span>
        <span class="meta-tag">水体状态：{{ entry['水体状态'] }}</span>
        <span class="meta-tag" :class="{ occupied: saving }">
          {{ saving ? '保存中…' : '可编辑' }}
        </span>
        <span class="meta-hint">两人同时编辑时，后到的一次保存会被拒绝并提示已被占用</span>
      </div>

      <form class="detail-grid" @submit.prevent="save">
        <label class="field">
          <span>水体编号</span>
          <input :value="entry['水体编号']" disabled />
        </label>
        <label class="field">
          <span>水体类型</span>
          <input v-model="form.values['水体类型']" />
        </label>
        <label class="field">
          <span>水体面积</span>
          <input v-model="form.values['水体面积']" />
        </label>
        <label class="field">
          <span>换水周期</span>
          <input v-model="form.values['换水周期']" />
        </label>
        <label class="field">
          <span>管护人员</span>
          <input v-model="form.values['管护人员']" />
        </label>
        <label class="field">
          <span>富营养化程度</span>
          <select v-model="form.values['富营养化']">
            <option v-for="level in eutrophyLevels" :key="level" :value="level">{{ level }}</option>
          </select>
        </label>
        <label class="field field-grade">
          <span>水质等级（一次只能调一级）</span>
          <select v-model="form.values['水质等级']">
            <option v-for="grade in qualityGrades" :key="grade" :value="grade">{{ grade }}</option>
          </select>
          <small v-if="gradeChanged" class="field-hint">
            由「{{ entry['水质等级'] }}」调整为「{{ form.values['水质等级'] }}」，须填写变更原因
          </small>
        </label>
        <label class="field field-reason">
          <span>变更原因{{ gradeChanged ? '（必填）' : '' }}</span>
          <textarea
            v-model="form.reason"
            rows="2"
            :placeholder="gradeChanged ? '调整水质等级必须说明依据，例如检测数据、污染来源' : '其他修改可简要说明'"
          ></textarea>
        </label>

        <div class="detail-actions">
          <button class="btn primary" type="submit" :disabled="saving">保存水体信息</button>
          <button
            v-for="action in actions"
            :key="action"
            class="btn"
            type="button"
            :disabled="saving"
            @click="runAction(action)"
          >
            {{ action }}
          </button>
        </div>
      </form>

      <p v-if="message" :class="messageOk ? 'ok-text' : 'error-text'">{{ message }}</p>

      <section class="history-block">
        <h3>水质等级变更记录</h3>
        <table v-if="entry.history?.length" class="data-table">
          <thead>
            <tr><th>时间</th><th>原等级</th><th>新等级</th><th>原因</th><th>操作人</th></tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in entry.history" :key="index">
              <td>{{ item.at }}</td>
              <td>{{ item.from }}</td>
              <td>{{ item.to }}</td>
              <td>{{ item.reason }}</td>
              <td>{{ item.operator }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="page-desc">暂无等级变更记录。</p>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'
import {
  ACTION_LABELS,
  EUTROPHY_LEVELS,
  QUALITY_GRADES,
  pickError,
} from './waterbody-shared'

type Entry = Record<string, any>

const route = useRoute()
const entryId = Number(route.params.id)

const qualityGrades = QUALITY_GRADES
const eutrophyLevels = EUTROPHY_LEVELS
const actions = ACTION_LABELS

const entry = ref<Entry | null>(null)
const loadError = ref('')
const saving = ref(false)
const message = ref('')
const messageOk = ref(false)

const form = reactive<{
  version: number
  reason: string
  values: Record<string, string>
}>({
  version: 0,
  reason: '',
  values: {},
})

const gradeChanged = computed(
  () => !!entry.value && form.values['水质等级'] !== entry.value['水质等级'],
)

function fillForm(data: Entry) {
  entry.value = data
  form.version = Number(data.version ?? 1)
  form.reason = ''
  form.values = {
    '水体类型': data['水体类型'] ?? '',
    '水体面积': data['水体面积'] ?? '',
    '换水周期': data['换水周期'] ?? '',
    '管护人员': data['管护人员'] ?? '',
    '水质等级': data['水质等级'] ?? QUALITY_GRADES[0],
    '富营养化': data['富营养化'] ?? EUTROPHY_LEVELS[0],
  }
}

async function load() {
  loadError.value = ''
  try {
    const response = await request(`/api/waterbody/${entryId}`)
    if (!response.ok) {
      throw new Error(await pickError(response, '水体明细读取失败'))
    }
    fillForm(await response.json())
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '水体明细读取失败'
  }
}

async function save() {
  message.value = ''
  saving.value = true
  try {
    const response = await request(`/api/waterbody/${entryId}`, {
      method: 'PUT',
      body: JSON.stringify({
        values: form.values,
        expected_version: form.version,
        reason: form.reason,
      }),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      // 409：已被他人占用或重复保存。提示后拉取最新版本，让用户基于最新数据再改。
      messageOk.value = false
      message.value = payload.detail ?? '保存失败，请刷新后重试'
      await load()
      return
    }
    messageOk.value = true
    message.value = payload.message ?? '已保存'
    fillForm(payload.entry)
  } catch (error) {
    messageOk.value = false
    message.value = error instanceof Error ? error.message : '保存失败'
  } finally {
    saving.value = false
  }
}

async function runAction(action: string) {
  message.value = ''
  saving.value = true
  try {
    const response = await request(`/api/waterbody/${entryId}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action, expected_version: form.version }),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      messageOk.value = false
      message.value = payload.detail ?? '动作未生效，请刷新后重试'
      await load()
      return
    }
    if (payload.ok === false) {
      messageOk.value = false
      message.value = payload.message ?? '动作未生效'
      await load()
      return
    }
    messageOk.value = true
    message.value = payload.message ?? '动作已执行'
    fillForm(payload.entry)
  } catch (error) {
    messageOk.value = false
    message.value = error instanceof Error ? error.message : '动作执行失败'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.meta-strip {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.meta-tag {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 12px;
  color: var(--muted);
}
.meta-tag.occupied {
  color: #b54708;
  border-color: #f0b429;
}
.meta-hint {
  font-size: 12px;
  color: var(--muted);
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
}
.field input,
.field select,
.field textarea {
  padding: 7px 9px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
  color: #1f2937;
}
.field input:disabled {
  background: #f1f5f9;
}
.field-grade,
.field-reason {
  grid-column: 1 / -1;
}
.field-hint {
  color: #b54708;
}
.detail-actions {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.ok-text {
  color: #067647;
  font-size: 13px;
}
.history-block {
  margin-top: 18px;
}
.history-block h3 {
  font-size: 14px;
  margin: 0 0 8px;
}
</style>
