'use client'

import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react'
import { useSearchParams } from 'next/navigation'
import {
  createDiscoverySession,
  getDiscoverySession,
  submitDiscoveryTurn,
} from '@/lib/api/endpoints/discovery'
import { fetchCollectedStatements, formatCollectedPreferenceChips } from '@/lib/api/endpoints/collected'
import { saveDiscoveryAsSubscription, fetchRecommendationCards } from '@/lib/api/endpoints/recommendation'  // ✅ 新增：导入fetchRecommendationCards
import { GatewayClientError, getErrorMessage, isAuthRequiredGatewayError } from '@/lib/api/errors'
import { confirmSessionOrRedirectToWelcome } from '@/lib/auth/confirm-session'
import { hydrateSessionFromAuthMe } from '@/lib/auth/hydrate-session'
import { getAccessToken, getProfileId } from '@/lib/auth/session'
import { canUseMockFallback } from '@/lib/mock'
import { notifyError, notifySuccess } from '@/lib/notify'
import { logDataProvenance, usePageDataSource } from '@/lib/data-provenance'
import { DEMO_CANDIDATES } from '@/lib/fixtures/demo-profiles'
import { getSSEServerUrl } from '@/lib/sse'
import {
  mapDiscoveryView,
  timelineHasCandidates,
  type DiscoveryTimelineItem,
  type MappedDiscoveryView,
} from '@/lib/discovery/map-discovery-view'
import {
  clearStoredDiscoverySessionId,
  readStoredDiscoverySessionId,
  writeStoredDiscoverySessionId,
} from '@/lib/discovery/session-storage'
import type { DiscoverySessionResponse } from '@/lib/types/discovery'

const SAVE_SUBSCRIPTION_ACTIONS = new Set([
  'save_subscription',
  'save_for_later',
  'create_subscription',
  'save_as_subscription',
])

function isNotFoundError(error: unknown): boolean {
  return error instanceof GatewayClientError && error.status === 404
}

function mergeCollectedChips(
  setCurrentPrefs: Dispatch<SetStateAction<string[]>>,
  statements: Record<string, unknown>,
) {
  const collectedChips = formatCollectedPreferenceChips(statements)
  if (!collectedChips.length) return
  setCurrentPrefs((prev) => {
    const merged = [...collectedChips]
    for (const chip of prev) {
      if (!merged.includes(chip)) merged.push(chip)
    }
    return merged.slice(0, 12)
  })
}

async function resolveDiscoverySession(
  profileId: number,
  sessionFromUrl: string | null,
): Promise<{ data: DiscoverySessionResponse; apiPath: string }> {
  const storedSessionId = readStoredDiscoverySessionId(profileId)
  const candidateSessionId = sessionFromUrl || storedSessionId

  if (candidateSessionId) {
    try {
      const restored = await getDiscoverySession(candidateSessionId)
      return {
        data: restored,
        apiPath: `/v1/discovery/sessions/${candidateSessionId}`,
      }
    } catch (error) {
      if (!isNotFoundError(error)) {
        throw error
      }
      clearStoredDiscoverySessionId(profileId)
    }
  }

  const created = await createDiscoverySession({ profileId })
  return { data: created, apiPath: '/v1/discovery/sessions' }
}

export function useDiscoverySession(onSessionIdChange?: (sessionId: string | null) => void) {
  const searchParams = useSearchParams()
  const sessionFromUrlQuery = searchParams.get('session')
  const [timelineItems, setTimelineItems] = useState<DiscoveryTimelineItem[]>([])
  const [inputValue, setInputValue] = useState('')
  const [currentPrefs, setCurrentPrefs] = useState<string[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [composerPlaceholder, setComposerPlaceholder] = useState('输入你的想法...')
  const [composerDisabled, setComposerDisabled] = useState(false)
  const [isSubmittingTurn, setIsSubmittingTurn] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const { usingMockData, applyProvenance } = usePageDataSource()
  const [isLoadingSession, setIsLoadingSession] = useState(true)
  const chatEndRef = useRef<HTMLDivElement>(null)
  const hasSessionCriteriaChipsRef = useRef(false)
  const autoPlayedAudioMessageIdsRef = useRef<Set<string>>(new Set())
  const pendingOpenPollRef = useRef<number | null>(null)

  // ✅ 新增：SSE连接管理
  const eventSourceRef = useRef<EventSource | null>(null)
  const sseConnectedRef = useRef(false)
  const [isSseConnected, setIsSseConnected] = useState(false)

  // ✅ 新增：防止新建会话后立即重复加载
  const isNewSessionJustCreatedRef = useRef(false)

  // ✅ 新增：标记新建会话正在进行中，防止loadSession useEffect重复触发
  const isCreatingNewSessionRef = useRef(false)

  const applyMappedView = useCallback((mapped: MappedDiscoveryView) => {
    const timelineItems = mapped.timelineItems.map((item) => {
      if (
        item.kind !== 'message' ||
        item.type !== 'matchmaker' ||
        item.mediaType !== 'audio' ||
        !item.mediaUrl
      ) {
        return item
      }

      const shouldAutoPlay =
        Boolean(item.isNewMessage) && !autoPlayedAudioMessageIdsRef.current.has(item.id)

      if (shouldAutoPlay) {
        autoPlayedAudioMessageIdsRef.current.add(item.id)
      }

      return {
        ...item,
        isNewMessage: shouldAutoPlay,
      }
    })

    console.log(
      '[DEBUG useDiscoverySession] mapped message items:',
      timelineItems
        .filter((item): item is Extract<DiscoveryTimelineItem, { kind: 'message' }> => item.kind === 'message')
        .map((item) => ({
          id: item.id,
          type: item.type,
          content: item.content,
          has_audio: item.mediaType === 'audio',
          mediaType: item.mediaType,
          mediaUrl: item.mediaUrl,
          mediaMetadata: item.mediaMetadata,
          isNewMessage: item.isNewMessage,
        })),
    )

    // DEBUG: 验证数据是否正确
    console.log('[DEBUG useDiscoverySession] timelineItems 数量:', timelineItems.length)
    console.log('[DEBUG useDiscoverySession] timelineItems:', timelineItems)
    const resultGroups = timelineItems.filter(i => i.kind === 'result_group')
    console.log('[DEBUG useDiscoverySession] result_group 数量:', resultGroups.length)
    if (resultGroups.length > 0) {
      console.log('[DEBUG useDiscoverySession] result_groups 详情:')
      resultGroups.forEach((rg, idx) => {
        console.log(`  [${idx}] id=${rg.id}, title=${rg.title}, candidates=${rg.candidates.length}`)
        rg.candidates.forEach((c, cIdx) => {
          console.log(`    candidate[${cIdx}]: id=${c.id}, name=${c.name}, city=${c.city}`)
        })
      })
    } else {
      console.warn('[DEBUG useDiscoverySession] ⚠️ 没有找到 result_group！候选人卡片不会显示')
    }
    setTimelineItems(timelineItems)
    hasSessionCriteriaChipsRef.current = Boolean(mapped.chips?.length)
    if (mapped.chips?.length) setCurrentPrefs(mapped.chips)
    setComposerPlaceholder(mapped.composerPlaceholder)
    setComposerDisabled(mapped.composerDisabled)
  }, [])

  const persistSessionId = useCallback(
    (profileId: number, sid: string) => {
      writeStoredDiscoverySessionId(profileId, sid)
      onSessionIdChange?.(sid)
    },
    [onSessionIdChange],
  )

  const applyDiscoveryResponse = useCallback(
    (data: DiscoverySessionResponse, profileId: number, apiPath: string) => {
      const sid = data.session?.session_id || null
      // DEBUG: 验证 API 返回的原始数据
      console.log('[DEBUG useDiscoverySession] API 返回数据:')
      console.log('  session_id:', sid)
      console.log('  view.timeline 数量:', data.view?.timeline?.length || 0)
      if (data.view?.timeline) {
        const messageItems = data.view.timeline.filter(
          (item) => item.item_type === 'assistant_message' || item.item_type === 'user_message',
        )
        console.log(
          '[DEBUG useDiscoverySession] 原始 message items:',
          messageItems.map((item) => ({
            item_id: item.item_id,
            item_type: item.item_type,
            body: item.body,
            created_at: item.created_at,
            has_metadata: Boolean(item.metadata),
            media_type: item.metadata?.media_type,
            media_url_present: Boolean(item.metadata?.media_url),
            media_metadata: item.metadata?.media_metadata,
          })),
        )
        const resultGroups = data.view.timeline.filter(i => i.item_type === 'result_group')
        console.log('  view.timeline 中 result_group 数量:', resultGroups.length)
        if (resultGroups.length > 0) {
          console.log('  view.timeline result_groups:')
          resultGroups.forEach((rg, idx) => {
            console.log(`    [${idx}] item_id=${rg.item_id}, cards=${rg.cards?.length || 0}`)
            if (rg.cards?.length) {
              rg.cards.forEach((card, cIdx) => {
                console.log(`      card[${cIdx}]: profile_id=${card.profile_id}, title=${card.title}`)
              })
            }
          })
        }
      }
      setSessionId(sid)
      if (sid) {
        persistSessionId(profileId, sid)
      } else {
        onSessionIdChange?.(null)
      }
      applyProvenance(false, true, apiPath)
      const mapped = mapDiscoveryView(data.view)
      applyMappedView(mapped)
      logDataProvenance('discover', applyProvenance(false, timelineHasCandidates(mapped.timelineItems), apiPath))
    },
    [applyMappedView, applyProvenance, onSessionIdChange, persistSessionId],
  )

  const loadCollectedPreferences = useCallback(
    (profileId: number, cancelled: () => boolean) => {
      void fetchCollectedStatements(profileId)
        .then((collected) => {
          if (cancelled()) return
          if (hasSessionCriteriaChipsRef.current) return
          mergeCollectedChips(setCurrentPrefs, collected.collected_statements || {})
        })
        .catch(() => {
          // Discovery view chips remain when collected API is unavailable.
        })
    },
    [],
  )

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [timelineItems, isSubmittingTurn])

  useEffect(() => {
    return () => {
      if (pendingOpenPollRef.current != null) {
        window.clearTimeout(pendingOpenPollRef.current)
      }
      // ✅ 新增：清理SSE连接
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
        sseConnectedRef.current = false
        setIsSseConnected(false)
      }
    }
  }, [])

  useEffect(() => {
    // ✅ 防止新建会话时触发loadSession useEffect重复执行
    if (isCreatingNewSessionRef.current) {
      console.log('[DEBUG loadSession] 正在创建新会话，跳过loadSession')
      return
    }

    let cancelled = false
    const isCancelled = () => cancelled

    async function loadSession() {
      setIsLoadingSession(true)
      setLoadError(null)
      hasSessionCriteriaChipsRef.current = false

      const sessionFromUrl = sessionFromUrlQuery?.trim() || null

      const existingProfileId = getProfileId()
      const shouldWaitForHydrate = Boolean(getAccessToken() && !existingProfileId)
      const authTask = getAccessToken() ? hydrateSessionFromAuthMe() : Promise.resolve(null)
      const authMeData = shouldWaitForHydrate ? await authTask : null
      if (cancelled) return
      if (!shouldWaitForHydrate) {
        void authTask
      }

      // ✅ 新增：检测用户是否完成onboarding
      const onboardingStatus = authMeData?.user?.onboarding_status || authMeData?.onboarding?.onboarding_status
      if (onboardingStatus === 'not_started') {
        setIsLoadingSession(false)
        setLoadError('请先完成资料填写后再使用发现与推荐')
        if (canUseMockFallback()) {
          applyProvenance(true, true, '/v1/discovery/sessions')
          setTimelineItems([
            {
              kind: 'message',
              id: 'demo-msg',
              type: 'matchmaker',
              content: '请先完成资料填写（演示数据）。',
              timestamp: '刚刚',
            },
          ])
        } else {
          applyProvenance(false, false, '/v1/discovery/sessions')
        }
        return
      }

      const profileId = existingProfileId ?? getProfileId()
      if (!profileId) {
        setIsLoadingSession(false)
        setLoadError(
          getAccessToken()
            ? '请先完成资料填写后再使用发现与推荐'
            : '未配置用户 ID，请在 .env.local 设置 NEXT_PUBLIC_HER_PROFILE_ID',
        )
        if (canUseMockFallback()) {
          applyProvenance(true, true, '/v1/discovery/sessions')
          setTimelineItems([
            {
              kind: 'message',
              id: 'demo-msg',
              type: 'matchmaker',
              content: '根据你的资料，我先帮你看了这几位（演示数据）。',
              timestamp: '刚刚',
            },
            {
              kind: 'result_group',
              id: 'demo-group',
              title: '为你精心挑选',
              candidates: DEMO_CANDIDATES,
            },
          ])
          setCurrentPrefs(['同城优先', '本科以上'])
        } else {
          applyProvenance(false, false, '/v1/discovery/sessions')
        }
        return
      }

      // ✅ 使用正确的profileId启动discovery任务（不会再有profile_id不匹配的问题）
      const discoveryTask = resolveDiscoverySession(profileId, sessionFromUrl)
      loadCollectedPreferences(profileId, isCancelled)

      try {
        const { data, apiPath } = await discoveryTask
        if (cancelled) return
        applyDiscoveryResponse(data, profileId, apiPath)
        const hasCandidates = timelineHasCandidates(mapDiscoveryView(data.view).timelineItems)
        const shouldPoll =
          data.session?.phase === 'collecting_preferences' &&
          !hasCandidates &&
          apiPath === '/v1/discovery/sessions'
        if (shouldPoll) {
          let attempts = 0
          const poll = () => {
            if (cancelled || !data.session?.session_id) return
            attempts += 1
            void getDiscoverySession(data.session.session_id)
              .then((refreshed) => {
                if (cancelled) return
                const refreshedHasCandidates = timelineHasCandidates(mapDiscoveryView(refreshed.view).timelineItems)
                applyDiscoveryResponse(
                  refreshed,
                  profileId,
                  `/v1/discovery/sessions/${data.session?.session_id}`,
                )
                if (!refreshedHasCandidates && attempts < 15) {
                  pendingOpenPollRef.current = window.setTimeout(poll, 1000)
                }
              })
              .catch(() => {
                if (attempts < 15) {
                  pendingOpenPollRef.current = window.setTimeout(poll, 1000)
                }
              })
          }
          pendingOpenPollRef.current = window.setTimeout(poll, 1000)
        }
      } catch (error) {
        if (cancelled) return
        if (isAuthRequiredGatewayError(error)) {
          const sessionStillValid = await confirmSessionOrRedirectToWelcome()
          if (!sessionStillValid) return
        }
        const message = getErrorMessage(error, '发现页会话加载失败')
        setLoadError(message)
        if (canUseMockFallback()) {
          applyProvenance(true, true, '/v1/discovery/sessions')
          setTimelineItems([
            {
              kind: 'message',
              id: 'demo-msg',
              type: 'matchmaker',
              content: '根据你的资料，我先帮你看了这几位（演示数据）。',
              timestamp: '刚刚',
            },
            {
              kind: 'result_group',
              id: 'demo-group',
              title: '为你精心挑选',
              candidates: DEMO_CANDIDATES,
            },
          ])
          setCurrentPrefs(['同城优先', '本科以上'])
        } else {
          applyProvenance(false, false, '/v1/discovery/sessions')
          notifyError(error, message)
        }
      } finally {
        if (!cancelled) setIsLoadingSession(false)
      }
    }

    void loadSession()
    return () => {
      cancelled = true
    }
  }, [applyDiscoveryResponse, applyProvenance, loadCollectedPreferences, sessionFromUrlQuery])

  const submitTurn = async (payload: { user_message?: string; action_id?: string }) => {
    if (!sessionId) {
      notifyError(new Error('会话未就绪'), '请稍后重试或刷新页面')
      return
    }

    const profileId = getProfileId()
    if (payload.action_id && SAVE_SUBSCRIPTION_ACTIONS.has(payload.action_id) && profileId) {
      setIsSubmittingTurn(true)
      try {
        await saveDiscoveryAsSubscription({ profileId })
        notifySuccess('已保存为长期留意')
      } catch (error) {
        notifyError(error, '保存订阅失败')
      } finally {
        setIsSubmittingTurn(false)
      }
    }

    const trimmedMessage = payload.user_message?.trim() || ''
    const optimisticId = trimmedMessage ? `optimistic-${Date.now()}` : null

    if (optimisticId && trimmedMessage) {
      setTimelineItems((prev) => [
        ...prev.filter((item) => item.kind !== 'suggested_actions'),
        {
          kind: 'message',
          id: optimisticId,
          type: 'user',
          content: trimmedMessage,
          timestamp: '刚刚',
        },
      ])
      setInputValue('')
    }

    setIsSubmittingTurn(true)
    try {
      const data = await submitDiscoveryTurn({
        sessionId,
        userMessage: trimmedMessage || undefined,
        actionId: payload.action_id,
      })
      const mapped = mapDiscoveryView(data.view)
      applyMappedView(mapped)
      if (profileId && sessionId) {
        writeStoredDiscoverySessionId(profileId, sessionId)
      }
    } catch (error) {
      if (isAuthRequiredGatewayError(error)) {
        const sessionStillValid = await confirmSessionOrRedirectToWelcome()
        if (!sessionStillValid) return
      }
      if (optimisticId) {
        setTimelineItems((prev) => prev.filter((item) => item.kind !== 'message' || item.id !== optimisticId))
        setInputValue(trimmedMessage)
      }
      notifyError(error, '发送失败，请重试')
    } finally {
      setIsSubmittingTurn(false)
    }
  }

  const reloadSession = useCallback(async () => {
    // ✅ 防止新建会话后立即重复加载
    if (isNewSessionJustCreatedRef.current) {
      console.log('[DEBUG reloadSession] 新建会话刚完成，跳过重复加载')
      return
    }

    const profileId = getProfileId()
    if (!profileId || !sessionId) return
    try {
      const restored = await getDiscoverySession(sessionId)
      applyDiscoveryResponse(restored, profileId, `/v1/discovery/sessions/${sessionId}`)
    } catch (error) {
      if (isAuthRequiredGatewayError(error)) {
        const sessionStillValid = await confirmSessionOrRedirectToWelcome()
        if (!sessionStillValid) return
      }
      notifyError(error, '刷新会话失败')
    }
  }, [applyDiscoveryResponse, sessionId])

  // ✅ 新增：SSE实时监听（候选人准备通知 + 推荐卡片推送）
  useEffect(() => {
    if (!sessionId) return
    const profileId = getProfileId()
    if (!profileId) return

    // 创建SSE连接
    const sseUrl = `${getSSEServerUrl()}/sse/discovery/${sessionId}?profile_id=${profileId}`
    const eventSource = new EventSource(sseUrl)
    eventSourceRef.current = eventSource

    eventSource.addEventListener('connected', (e) => {
      console.log('[Discovery SSE] Connected:', e.data)
      sseConnectedRef.current = true
      setIsSseConnected(true)
    })

    eventSource.addEventListener('message', (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.type === 'candidates_ready') {
          console.log('[Discovery SSE] 候选人准备好了:', data)
          // 候选人准备好了，立即获取最新数据
          void reloadSession()
        } else if (data.type === 'new_recommendation') {
          console.log('[Discovery SSE] 新推荐卡片:', data)
          // 新推荐卡片推送（被动推荐 + 主动推荐）
          // 立即刷新推荐卡片列表
          void fetchRecommendationCards(profileId).then((response) => {
            // 触发事件通知徽章更新
            if (typeof window !== 'undefined' && typeof CustomEvent === 'function') {
              window.dispatchEvent(new CustomEvent('her:recommendation-read-state-changed', {
                detail: { profileId, newCards: response.cards },
              }))
            }
          })
        }
      } catch (err) {
        console.error('[Discovery SSE] Parse error:', err)
      }
    })

    eventSource.addEventListener('heartbeat', (e) => {
      console.log('[Discovery SSE] Heartbeat:', e.data)
    })

    eventSource.onerror = (e) => {
      const readyState = eventSource.readyState
      if (readyState === EventSource.CONNECTING) {
        console.warn('[Discovery SSE] Reconnecting...', { readyState })
      } else if (readyState === EventSource.CLOSED) {
        console.error('[Discovery SSE] Closed', { readyState, event: e })
      } else {
        console.warn('[Discovery SSE] Error event', { readyState, event: e })
      }
      sseConnectedRef.current = false
      setIsSseConnected(false)
      // EventSource会自动重连
    }

    return () => {
      eventSource.close()
      eventSourceRef.current = null
      sseConnectedRef.current = false
      setIsSseConnected(false)
    }
  }, [sessionId, reloadSession])

  // ✅ 新增：SSE兜底机制：连接失败时回退到轮询
  useEffect(() => {
    if (!sessionId) return
    if (isSseConnected) return // SSE已连接，不需要轮询兜底

    const profileId = getProfileId()
    if (!profileId) return

    console.log('[Discovery SSE] SSE未连接，启动轮询兜底')

    // 初始加载
    void reloadSession()

    // 30秒轮询兜底
    const interval = setInterval(async () => {
      await reloadSession()
    }, 30000)

    return () => clearInterval(interval)
  }, [sessionId, isSseConnected, reloadSession])

  // 新增：创建新会话
  const createNewSession = useCallback(async () => {
    const profileId = getProfileId()
    if (!profileId) return null

    // ✅ 标记正在创建新会话，防止loadSession useEffect重复触发
    isCreatingNewSessionRef.current = true
    console.log('[DEBUG createNewSession] 开始创建新会话，设置防触发标记')

    setIsLoadingSession(true)
    try {
      const created = await createDiscoverySession({ profileId })
      const sid = created.session?.session_id || null
      if (sid) {
        // ✅ 标记新建会话已完成，防止后续立即重复加载
        isNewSessionJustCreatedRef.current = true
        applyDiscoveryResponse(created, profileId, '/v1/discovery/sessions')
        notifySuccess('已创建新会话')

        // ✅ 等待1秒后解除标记，让后续的SSE/轮询可以正常工作
        setTimeout(() => {
          isNewSessionJustCreatedRef.current = false
          isCreatingNewSessionRef.current = false
          console.log('[DEBUG createNewSession] 解除所有防重复标记')
        }, 1000)
      }
      return sid
    } catch (error) {
      if (isAuthRequiredGatewayError(error)) {
        const sessionStillValid = await confirmSessionOrRedirectToWelcome()
        if (!sessionStillValid) return null
      }
      notifyError(error, '创建新会话失败')
      return null
    } finally {
      setIsLoadingSession(false)
    }
  }, [applyDiscoveryResponse])

  // 新增：切换到指定会话
  const switchSession = useCallback(async (targetSessionId: string) => {
    const profileId = getProfileId()
    if (!profileId) return
    setIsLoadingSession(true)
    try {
      const restored = await getDiscoverySession(targetSessionId)
      applyDiscoveryResponse(restored, profileId, `/v1/discovery/sessions/${targetSessionId}`)
    } catch (error) {
      if (isAuthRequiredGatewayError(error)) {
        const sessionStillValid = await confirmSessionOrRedirectToWelcome()
        if (!sessionStillValid) return
      }
      notifyError(error, '切换会话失败')
    } finally {
      setIsLoadingSession(false)
    }
  }, [applyDiscoveryResponse])

  // 新增：添加消息到对话历史（用于测评完成后添加小雅消息）
  const addTimelineItem = useCallback((item: DiscoveryTimelineItem) => {
    setTimelineItems((prev) => [...prev, item])
  }, [])

  const removeSuggestedActions = useCallback(() => {
    setTimelineItems((prev) => prev.filter((item) => item.kind !== 'suggested_actions'))
  }, [])

  // 新增：移除指定消息（用于移除临时消息）
  const removeTimelineItem = useCallback((itemId: string) => {
    setTimelineItems((prev) => prev.filter((item) => item.id !== itemId))
  }, [])

  return {
    timelineItems,
    inputValue,
    setInputValue,
    isTyping: isSubmittingTurn,
    currentPrefs,
    composerPlaceholder,
    composerDisabled,
    isSubmittingTurn,
    loadError,
    usingMockData,
    isLoadingSession,
    chatEndRef,
    submitTurn,
    sessionId,
    reloadSession,
    createNewSession,  // 新增：创建新会话
    switchSession,  // 新增：切换会话
    addTimelineItem,  // 新增
    removeTimelineItem,  // 新增：移除指定消息
    removeSuggestedActions,
  }
}
