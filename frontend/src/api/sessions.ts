import type {
  CreateSessionData,
  PlanState,
  RunMode,
  SendMessageData,
} from '@/types/contract'

import { apiCall, type ApiResult } from './client'

/** `CONTRACTS.md` §13.1 的三个会话接口。攻略接口属于 C7，尚未提供。 */

export function createSession(runMode: RunMode = 'DEMO'): Promise<ApiResult<CreateSessionData>> {
  // 契约必填 run_mode；不传会被 422 拒掉
  return apiCall<CreateSessionData>({
    url: '/api/sessions',
    method: 'post',
    data: { run_mode: runMode },
  })
}

export function sendMessage(
  sessionId: string,
  text: string,
  expectedProfileVersion?: number | null,
): Promise<ApiResult<SendMessageData>> {
  return apiCall<SendMessageData>({
    url: `/api/sessions/${encodeURIComponent(sessionId)}/messages`,
    method: 'post',
    data: {
      text,
      expected_profile_version: expectedProfileVersion ?? null,
    },
  })
}

export function getSession(sessionId: string): Promise<ApiResult<PlanState>> {
  return apiCall<PlanState>({
    url: `/api/sessions/${encodeURIComponent(sessionId)}`,
    method: 'get',
  })
}
