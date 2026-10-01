/** 水体养护列表页与详情页共用的口径，保证两边读到、展示的是同一份数据定义。 */

export const ENDPOINT = '/api/waterbody'

export const COLUMNS = [
  '水体编号',
  '水体类型',
  '水体面积',
  '水质等级',
  '富营养化',
  '换水周期',
  '管护人员',
  '水体状态',
] as const

/** 水质等级：与后端 QUALITY_GRADES 保持一致，顺序即由好到坏。 */
export const QUALITY_GRADES = ['Ⅰ类', 'Ⅱ类', 'Ⅲ类', 'Ⅳ类', 'Ⅴ类', '劣Ⅴ类'] as const

/** 富营养化程度：与后端 EUTROPHY_LEVELS 保持一致。 */
export const EUTROPHY_LEVELS = [
  '无',
  '贫营养',
  '中营养',
  '轻度富营养',
  '中度富营养',
  '重度富营养',
] as const

export const STATUSES = ['良好', '轻度污染', '重度污染', '净化中', '已净化'] as const

export const ACTION_LABELS = ['记录污染', '净化处理', '验收净化'] as const

/** 各动作允许的当前状态，用于在列表上禁用当前不可执行的按钮。 */
export const ACTION_ALLOWED_FROM: Record<string, string[]> = {
  记录污染: ['良好', '轻度污染'],
  净化处理: ['重度污染'],
  验收净化: ['净化中'],
}

export type WaterbodyRow = {
  id: number
  version: number
  '水体编号': string
  '水体类型': string
  '水体面积': string
  '水质等级': string
  '富营养化': string
  '换水周期': string
  '管护人员': string
  '水体状态': string
}

/** 统一解析后端错误：HTTPException 返回 {detail}，ActionResult 返回 {message}。 */
export async function pickError(response: Response, fallback: string): Promise<string> {
  try {
    const payload = await response.json()
    return payload.detail ?? payload.message ?? fallback
  } catch {
    return fallback
  }
}
