'use client'

import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react'
import { useSearchParams } from 'next/navigation'
import {
  createDiscoverySession,
  getDiscoverySession,
  submitDiscoveryTurn,
} from '@/lib/api/endpoints/discovery'
import { fetchCollectedStatements, formatCollectedPreferenceChips } from '@/lib/api/endpoints/collected'
import { saveDiscoveryAsSubscription } from '@/lib/api/endpoints/recommendation'
import { GatewayClientError, getErrorMessage } from '@/lib/api/errors'
import { hydrateSessionFromAuthMe } from '@/lib/auth/hydrate-session'
import { getAccessToken, getProfileId } from '@/lib/auth/session'
import { canUseMockFallback } from '@/lib/mock'
import { notifyError, notifySuccess } from '@/lib/notify'
import { logDataProvenance, usePageDataSource } from '@/lib/data-provenance'
import { DEMO_CANDIDATES } from '@/lib/fixtures/demo-profiles'
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
    let cancelled = false
    const isCancelled = () => cancelled

    async function loadSession() {
      setIsLoadingSession(true)
      setLoadError(null)
      hasSessionCriteriaChipsRef.current = false

      const sessionFromUrl = sessionFromUrlQuery?.trim() || null

      // ✅ 修复：先等待hydrate完成，再获取profileId（防止使用环境变量的默认值导致Gateway报错）
      const authTask = getAccessToken() ? hydrateSessionFromAuthMe() : Promise.resolve(null)
      const authMeData = await authTask  // 等待hydrate完成，并获取返回数据
      if (cancelled) return

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

      const profileId = getProfileId()  // hydrate完成后获取正确的profileId
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
      } catch (error) {
        if (cancelled) return
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
    const profileId = getProfileId()
    if (!profileId || !sessionId) return
    try {
      const restored = await getDiscoverySession(sessionId)
      applyDiscoveryResponse(restored, profileId, `/v1/discovery/sessions/${sessionId}`)
    } catch (error) {
      notifyError(error, '刷新会话失败')
    }
  }, [applyDiscoveryResponse, sessionId])

  // 新增：创建新会话
  const createNewSession = useCallback(async () => {
    const profileId = getProfileId()
    if (!profileId) return null
    setIsLoadingSession(true)
    try {
      const created = await createDiscoverySession({ profileId })
      const sid = created.session?.session_id || null
      if (sid) {
        applyDiscoveryResponse(created, profileId, '/v1/discovery/sessions')
        notifySuccess('已创建新会话')
      }
      return sid
    } catch (error) {
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
