import type {
  ConfirmGuideData,
  ConfirmGuideRequest,
  GetGuideData,
  GuideChangeData,
  UserAction,
} from '@/types/contract'

import { apiCall, type ApiResult } from './client'

/**
 * `CONTRACTS.md` §13.2 的四个攻略接口（C7 已实现，统一响应信封）。
 *
 * 错误一律按 `error.code` 判定，不要看 HTTP 状态码猜：
 * - 404 `DATA_MISSING`：攻略不存在（旧版本被新版本替换后也会命中这一条）
 * - 409 `VERSION_CONFLICT`：`expected_guide_version` 过期，先刷新再改
 * - 409 `DATA_MISSING`：素材缺失，`error.details` 里写明缺什么
 *   （例如 `LODGING_CANDIDATES`）——**后端不会给半个攻略，缺就是缺**。
 */

/** `GET /api/guides/{id}?version=` —— 取七部分攻略；不传 `version` 取最新版。 */
export function getGuide(
  guideId: string,
  version?: number | null,
): Promise<ApiResult<GetGuideData>> {
  return apiCall<GetGuideData>({
    url: `/api/guides/${encodeURIComponent(guideId)}`,
    method: 'get',
    params: version === null || version === undefined ? undefined : { version },
  })
}

/** `POST /api/guides/{id}/confirm` —— 确认攻略并锁定节点，`guide_version` +1。 */
export function confirmGuide(
  guideId: string,
  payload: ConfirmGuideRequest,
): Promise<ApiResult<ConfirmGuideData>> {
  return apiCall<ConfirmGuideData>({
    url: `/api/guides/${encodeURIComponent(guideId)}/confirm`,
    method: 'post',
    data: payload,
  })
}

/**
 * `POST /api/guides/{id}/modify` —— 按 `UserAction` 改攻略，返回新版本与版本谱系。
 *
 * B7 暂时只把 `confirm` 与 `incident` 接进了页面。这条保留是因为
 * `CONTRACTS.md` §13.2 就是这四个接口，客户端应把整组接口签完；
 * 改成"有页面入口才写函数"会让下一个接手的人以为契约少了一条。
 * 接页面时直接复用，不需要新写请求层。
 */
export function modifyGuide(
  guideId: string,
  action: UserAction,
): Promise<ApiResult<GuideChangeData>> {
  return apiCall<GuideChangeData>({
    url: `/api/guides/${encodeURIComponent(guideId)}/modify`,
    method: 'post',
    data: { action },
  })
}

/** `POST /api/guides/{id}/incident` —— 上报突发（「今天下雨了」），触发重规划。 */
export function reportIncident(
  guideId: string,
  action: UserAction,
): Promise<ApiResult<GuideChangeData>> {
  return apiCall<GuideChangeData>({
    url: `/api/guides/${encodeURIComponent(guideId)}/incident`,
    method: 'post',
    data: { action },
  })
}
