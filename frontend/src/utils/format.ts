import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'

dayjs.extend(utc)

/** ISO 日期时间且不带时区标记（后端下发的形式）。 */
const NAIVE_ISO = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/
const HAS_TZ = /([zZ]|[+-]\d{2}:?\d{2})$/

/** 解析后端时间串。
 *
 * 后端所有时间都以 `datetime.utcnow()` 写入，序列化后形如 `2026-08-23T07:30:19`，
 * **没有时区后缀**。直接交给 dayjs 会被当成浏览器本地时间——曼谷的用户在
 * 14:30 登录，审计日志里却显示 07:30，整整差 7 小时且没有任何标注。
 * 审计时间是合规追溯的核心证据，这种偏差不能留。
 *
 * 这里显式按 UTC 解析再转成阅读者本地时区；已带时区的串保持原样解析。
 */
function parseServerTime(s: string) {
  return NAIVE_ISO.test(s) && !HAS_TZ.test(s) ? dayjs.utc(s).local() : dayjs(s)
}

export function formatSize(bytes: number): string {
  if (!bytes && bytes !== 0) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

export function formatTime(s?: string | null): string {
  if (!s) return '-'
  return parseServerTime(s).format('YYYY-MM-DD HH:mm')
}

/** 纯日期（如截止日 `2026-10-15`）不做时区换算：
 *  它表达的是业务日期而非时刻，按 UTC 换算会在负时区把日期整体前移一天。 */
export function formatDate(s?: string | null): string {
  if (!s) return '-'
  return dayjs(s).format('YYYY-MM-DD')
}
