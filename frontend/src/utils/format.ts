import dayjs from 'dayjs'

export function formatSize(bytes: number): string {
  if (!bytes && bytes !== 0) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

export function formatTime(s?: string | null): string {
  if (!s) return '-'
  return dayjs(s).format('YYYY-MM-DD HH:mm')
}

export function formatDate(s?: string | null): string {
  if (!s) return '-'
  return dayjs(s).format('YYYY-MM-DD')
}
