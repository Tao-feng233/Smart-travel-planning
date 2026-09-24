import axios, { type AxiosError, type AxiosRequestConfig } from 'axios'

import type { Envelope, ErrorDetail, WarningItem } from '@/types/contract'

/**
 * 统一响应信封的客户端（CONTRACTS.md §13）。
 *
 * 两条必须记住的约定：
 * 1. **缺失字段、模拟数据、覆盖不足都不是 HTTP 错误**，而是正常工作流状态
 *    或 `warnings`。所以前端不能看到 4xx 就当失败，要看 `ok` 与 `error`。
 * 2. 前端**不持有任何服务端 Key**，请求只走同源代理（vite.config.ts）。
 */

/** §13.3 的 8 个错误码 → 面向用户的中文说明。 */
const ERROR_TEXT: Record<string, string> = {
  CONTRACT_MISMATCH: '请求与契约不匹配，请联系开发排查。',
  VERSION_CONFLICT: '数据版本已过期，请刷新后重试。',
  OUT_OF_KNOWLEDGE_COVERAGE: '当前知识库不覆盖这个需求。',
  DATA_MISSING: '找不到对应的会话或数据。',
  NO_FEASIBLE_PLAN: '在当前条件下没有可行方案。',
  DATA_EXPIRED: '数据已过期，需要刷新。',
  VALIDATION_FAILED: '计划未通过验证。',
  PROVIDER_UNAVAILABLE: '外部数据源暂时不可用。',
}

export class ApiError extends Error {
  readonly code: string
  readonly details: Record<string, string>
  readonly traceId: string | null

  constructor(detail: ErrorDetail, traceId: string | null) {
    super(ERROR_TEXT[detail.code] ?? detail.message ?? '请求失败')
    this.name = 'ApiError'
    this.code = detail.code
    this.details = detail.details ?? {}
    this.traceId = traceId
  }
}

export interface ApiResult<T> {
  data: T
  warnings: WarningItem[]
  traceId: string | null
}

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 120000,
  headers: { 'Content-Type': 'application/json' },
})

export async function apiCall<T>(config: AxiosRequestConfig): Promise<ApiResult<T>> {
  try {
    const response = await http.request<Envelope<T>>(config)
    const envelope = response.data

    if (!envelope || typeof envelope !== 'object' || !('ok' in envelope)) {
      throw new ApiError(
        {
          code: 'CONTRACT_MISMATCH',
          message: '响应体不是 {ok, data, warnings, error, trace_id} 信封结构',
          details: {},
        },
        null,
      )
    }
    if (!envelope.ok || envelope.data === null || envelope.data === undefined) {
      throw new ApiError(
        envelope.error ?? {
          code: 'CONTRACT_MISMATCH',
          message: '接口返回 ok=false 但没有给出 error',
          details: {},
        },
        envelope.trace_id ?? null,
      )
    }
    return {
      data: envelope.data,
      warnings: envelope.warnings ?? [],
      traceId: envelope.trace_id ?? null,
    }
  } catch (error) {
    if (error instanceof ApiError) {
      throw error
    }
    throw toApiError(error as AxiosError)
  }
}

function toApiError(error: AxiosError): ApiError {
  // FastAPI 用 HTTPException(detail=Envelope(...)) 抛错，所以错误信封藏在 detail 里
  const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
  if (detail && typeof detail === 'object' && 'code' in (detail as Record<string, unknown>)) {
    const parsed = detail as ErrorDetail & { trace_id?: string | null }
    return new ApiError(parsed, parsed.trace_id ?? null)
  }
  if (error.code === 'ECONNABORTED') {
    return new ApiError(
      { code: 'PROVIDER_UNAVAILABLE', message: '请求超时，请稍后重试。', details: {} },
      null,
    )
  }
  if (!error.response) {
    return new ApiError(
      {
        code: 'PROVIDER_UNAVAILABLE',
        message: '连不上后端服务。请先启动：cd backend && python -m uvicorn app.main:app --reload',
        details: {},
      },
      null,
    )
  }
  return new ApiError(
    {
      code: 'PROVIDER_UNAVAILABLE',
      message: `后端返回 ${error.response.status}`,
      details: {},
    },
    null,
  )
}
