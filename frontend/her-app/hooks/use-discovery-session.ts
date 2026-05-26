'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
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

  const hydrateFromResponse = useCallback(
    async (data: DiscoverySessionResponse, profileId: number, apiPath: string) => {
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
      try {
        const collected = await fetchCollectedStatements(profileId)
        const collectedChips = formatCollectedPreferenceChips(collected.collected_statements || {})
        if (collectedChips.length) {
          setCurrentPrefs((prev) => {
            const merged = [...collectedChips]
            for (const chip of prev) {
              if (!merged.includes(chip)) merged.push(chip)
            }
            return merged.slice(0, 12)
          })
        }
      } catch {
        // Discovery view chips remain when collected API is unavailable.
      }
      logDataProvenance('discover', applyProvenance(false, mapped.candidates.length > 0, apiPath))
    },
    [applyMappedView, applyProvenance, onSessionIdChange, persistSessionId],
  )

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, suggestedActions, backendCandidates])

  useEffect(() => {
    let cancelled = false

    async function loadSession() {
      if (getAccessToken()) {
        await hydrateSessionFromAuthMe()
      }
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

      setIsLoadingSession(true)
      setLoadError(null)
      const sessionFromUrl = sessionFromUrlQuery?.trim() || null
      const storedSessionId = readStoredDiscoverySessionId(profileId)
      const candidateSessionId = sessionFromUrl || storedSessionId

      try {
        if (candidateSessionId) {
          try {
            const restored = await getDiscoverySession(candidateSessionId)
            if (cancelled) return
            await hydrateFromResponse(
              restored,
              profileId,
              `/v1/discovery/sessions/${candidateSessionId}`,
            )
            return
          } catch (error) {
            if (!isNotFoundError(error)) {
              throw error
            }
            clearStoredDiscoverySessionId(profileId)
          }
        }

        const created = await createDiscoverySession({ profileId })
        if (cancelled) return
        await hydrateFromResponse(created, profileId, '/v1/discovery/sessions')
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
  }, [applyProvenance, hydrateFromResponse, sessionFromUrlQuery])

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

    setIsSubmittingTurn(true)
    try {
      const data = await submitDiscoveryTurn({
        sessionId,
        userMessage: payload.user_message,
        actionId: payload.action_id,
      })
      const mapped = mapDiscoveryView(data.view)
      applyMappedView(mapped)
      if (profileId && sessionId) {
        writeStoredDiscoverySessionId(profileId, sessionId)
      }
      if (payload.user_message) setInputValue('')
    } catch (error) {
      notifyError(error, '发送失败，请重试')
    } finally {
      setIsSubmittingTurn(false)
    }
  }

  return {
    messages,
    inputValue,
    setInputValue,
    isTyping: false,
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
