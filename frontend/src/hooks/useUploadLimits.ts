import { useEffect, useState } from 'react'
import { auth } from '@/api/endpoints'

interface Limits { max_file_mb: number; allowed_extensions: string[] }

/** 上传限制（由后端下发）。
 *
 * 不在前端写死数字：改了后端却忘了改前端，用户就会遇到"界面说可以传、
 * 传完却被拒"。拿不到时返回 null，调用方跳过预检、交由后端把关——
 * 宁可少一道预检，也不能凭一个可能过期的常量误拒用户的合法文件。
 */
export function useUploadLimits(): Limits | null {
  const [limits, setLimits] = useState<Limits | null>(null)
  useEffect(() => { auth.limits().then(setLimits).catch(() => setLimits(null)) }, [])
  return limits
}

/** 逐个预检文件大小；返回超限文件名列表（空表示全部通过）。 */
export function oversizeNames(files: File[], limits: Limits | null): string[] {
  if (!limits) return []
  const max = limits.max_file_mb * 1024 * 1024
  return files.filter((f) => f.size > max).map((f) => f.name)
}
