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
import type { CandidatePreview } from '@/lib/types/candidate'
import {
  mapDiscoveryView,
  type DiscoveryChatMessage,
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
  const [messages, setMessages] = useState<DiscoveryChatMessage[]>([])
  const [inputValue, setInputValue] = useState('')
  const [currentPrefs, setCurrentPrefs] = useState<string[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [suggestedActions, setSuggestedActions] = useState<Array<{ action_id: string; label: string }>>([])
  const [composerPlaceholder, setComposerPlaceholder] = useState('输入你的想法...')
  const [composerDisabled, setComposerDisabled] = useState(false)
  const [isSubmittingTurn, setIsSubmittingTurn] = useState(false)
  const [backendCandidates, setBackendCandidates] = useState<CandidatePreview[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const { usingMockData, applyProvenance } = usePageDataSource()
  const [isLoadingSession, setIsLoadingSession] = useState(true)
  const chatEndRef = useRef<HTMLDivElement>(null)

  const applyMappedView = useCallback((mapped: MappedDiscoveryView) => {
    setMessages(mapped.messages)
    if (mapped.chips?.length) setCurrentPrefs(mapped.chips)
    setSuggestedActions(mapped.actions)
    setComposerPlaceholder(mapped.composerPlaceholder)
    setComposerDisabled(mapped.composerDisabled)
    setBackendCandidates(mapped.candidates.length ? mapped.candidates : [])
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
      setSessionId(sid)
      if (sid) {
        persistSessionId(profileId, sid)
      } else {
        onSessionIdChange?.(null)
      }
      applyProvenance(false, true, apiPath)
      const mapped = mapDiscoveryView(data.view)
      applyMappedView(mapped)
      logDataProvenance('discover', applyProvenance(false, mapped.candidates.length > 0, apiPath))
    },
    [applyMappedView, applyProvenance, onSessionIdChange, persistSessionId],
  )

  const loadCollectedPreferences = useCallback(
    (profileId: number, cancelled: () => boolean) => {
      void fetchCollectedStatements(profileId)
        .then((collected) => {
          if (cancelled()) return
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
  }, [messages, suggestedActions, backendCandidates, isSubmittingTurn])

  useEffect(() => {
    let cancelled = false
    const isCancelled = () => cancelled

    async function loadSession() {
      setIsLoadingSession(true)
      setLoadError(null)

      const sessionFromUrl = sessionFromUrlQuery?.trim() || null
      const authTask = getAccessToken() ? hydrateSessionFromAuthMe() : Promise.resolve(null)

      const profileIdBeforeAuth = getProfileId()
      let discoveryTask: Promise<{ data: DiscoverySessionResponse; apiPath: string }> | null =
        profileIdBeforeAuth
          ? resolveDiscoverySession(profileIdBeforeAuth, sessionFromUrl)
          : null

      if (profileIdBeforeAuth) {
        loadCollectedPreferences(profileIdBeforeAuth, isCancelled)
      }

      await authTask
      if (cancelled) return

      const profileId = getProfileId()
      if (!profileId) {
        setIsLoadingSession(false)
        setLoadError(
          getAccessToken()
            ? '请先完成资料填写后再使用发现与推荐'
            : '未配置用户 ID，请在 .env.local 设置 NEXT_PUBLIC_HER_PROFILE_ID',
        )
        if (canUseMockFallback()) {
          applyProvenance(true, true, '/v1/discovery/sessions')
          setBackendCandidates(DEMO_CANDIDATES)
          setCurrentPrefs(['同城优先', '本科以上'])
        } else {
          applyProvenance(false, false, '/v1/discovery/sessions')
        }
        return
      }

      if (!discoveryTask || profileId !== profileIdBeforeAuth) {
        loadCollectedPreferences(profileId, isCancelled)
        discoveryTask = resolveDiscoverySession(profileId, sessionFromUrl)
      }

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
          setBackendCandidates(DEMO_CANDIDATES)
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
      setMessages((prev) => [
        ...prev,
        {
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
        setMessages((prev) => prev.filter((message) => message.id !== optimisticId))
        setInputValue(trimmedMessage)
      }
      notifyError(error, '发送失败，请重试')
    } finally {
      setIsSubmittingTurn(false)
    }
  }

  return {
    messages,
    inputValue,
    setInputValue,
    isTyping: isSubmittingTurn,
    currentPrefs,
    suggestedActions,
    composerPlaceholder,
    composerDisabled,
    isSubmittingTurn,
    backendCandidates,
    loadError,
    usingMockData,
    isLoadingSession,
    chatEndRef,
    submitTurn,
  }
}
