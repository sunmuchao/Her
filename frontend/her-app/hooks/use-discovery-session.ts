'use client'

import { useEffect, useRef, useState } from 'react'
import { createDiscoverySession, submitDiscoveryTurn } from '@/lib/api/endpoints/discovery'
import { fetchCollectedStatements, formatCollectedPreferenceChips } from '@/lib/api/endpoints/collected'
import { saveDiscoveryAsSubscription } from '@/lib/api/endpoints/recommendation'
import { getErrorMessage } from '@/lib/api/errors'
import { hydrateSessionFromAuthMe } from '@/lib/auth/hydrate-session'
import { getAccessToken, getProfileId } from '@/lib/auth/session'
import { canUseMockFallback } from '@/lib/mock'
import { notifyError, notifySuccess } from '@/lib/notify'
import { logDataProvenance, usePageDataSource } from '@/lib/data-provenance'
import { DEMO_CANDIDATES } from '@/lib/fixtures/demo-profiles'
import type { CandidatePreview } from '@/lib/types/candidate'
import { mapDiscoveryView, type DiscoveryChatMessage } from '@/lib/discovery/map-discovery-view'

const SAVE_SUBSCRIPTION_ACTIONS = new Set([
  'save_subscription',
  'save_for_later',
  'create_subscription',
  'save_as_subscription',
])

const initialMessages: DiscoveryChatMessage[] = [
  { id: '1', type: 'matchmaker', content: '你好，我是你的专属红娘小雅。接下来我会帮你找到那个对的人。', timestamp: '09:30' },
  { id: '2', type: 'matchmaker', content: '你理想中的伴侣是什么样的？', timestamp: '09:31' },
]

export function useDiscoverySession(onSessionIdChange?: (sessionId: string | null) => void) {
  const [messages, setMessages] = useState(initialMessages)
  const [inputValue, setInputValue] = useState('')
  const [isTyping, setIsTyping] = useState(false)
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

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsTyping(true)
      setTimeout(() => setIsTyping(false), 2500)
    }, 1500)
    return () => clearTimeout(timer)
  }, [])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping, suggestedActions, backendCandidates])

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
      try {
        const data = await createDiscoverySession({ profileId })
        if (cancelled) return
        const sid = data.session?.session_id || null
        setSessionId(sid)
        onSessionIdChange?.(sid)
        applyProvenance(false, true, '/v1/discovery/sessions')
        const mapped = mapDiscoveryView(data.view)
        if (mapped.messages.length) setMessages(mapped.messages)
        if (mapped.chips?.length) setCurrentPrefs(mapped.chips)
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
        setSuggestedActions(mapped.actions)
        setComposerPlaceholder(mapped.composerPlaceholder)
        setComposerDisabled(mapped.composerDisabled)
        setBackendCandidates(mapped.candidates.length ? mapped.candidates : [])
        logDataProvenance('discover', applyProvenance(false, mapped.candidates.length > 0, '/v1/discovery/sessions'))
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
  }, [onSessionIdChange, applyProvenance])

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
      if (mapped.messages.length) setMessages(mapped.messages)
      if (mapped.chips) setCurrentPrefs(mapped.chips)
      setSuggestedActions(mapped.actions)
      setComposerPlaceholder(mapped.composerPlaceholder)
      setComposerDisabled(mapped.composerDisabled)
      setBackendCandidates(mapped.candidates.length ? mapped.candidates : [])
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
    isTyping,
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
