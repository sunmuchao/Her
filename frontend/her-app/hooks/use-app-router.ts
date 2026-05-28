'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import type { CandidatePreview } from '@/lib/types/candidate'
import { DEMO_DEFAULT_CANDIDATE_ID, DEMO_DEFAULT_CHAT_ID } from '@/lib/navigation/defaults'
import { pageToPath, pathToPage } from '@/lib/navigation/routes'
import type { AppPage, SubView, TabType } from '@/lib/navigation/types'

function pageToTab(page: AppPage): TabType {
  if (page === 'main-relationships' || page === 'sub-chat') return 'relationships'
  if (page === 'main-profile' || page === 'sub-trust-center' || page === 'sub-collected-preferences') return 'profile'
  return 'matchmaker'
}

function pageToSubView(page: AppPage): SubView {
  if (page === 'sub-recommendation-inbox') return 'recommendation-inbox'
  if (page === 'sub-candidate-detail') return 'candidate-detail'
  if (page === 'sub-chat') return 'chat'
  if (page === 'sub-verification') return 'verification'
  if (page === 'sub-trust-center') return 'trust-center'
  if (page === 'sub-collected-preferences') return 'collected-preferences'
  return 'main'
}

export type ChatUserInfo = {
  title?: string
  avatar?: string
  caseId?: string
  counterpartId?: string
}

export function useAppRouter() {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const parsed = useMemo(() => pathToPage(pathname), [pathname])
  const currentPage = parsed.page
  const currentTab = pageToTab(currentPage)
  const subView = pageToSubView(currentPage)

  const [selectedCandidate, setSelectedCandidate] = useState<CandidatePreview | null>(null)
  const [discoverySessionId, setDiscoverySessionId] = useState<string | null>(null)

  // DEBUG: 监控 selectedCandidate 状态变化
  useEffect(() => {
    console.log('[useAppRouter] selectedCandidate 状态变化:', selectedCandidate)
  }, [selectedCandidate])

  const selectedCandidateId =
    parsed.candidateId ??
    (currentPage === 'sub-candidate-detail' ? DEMO_DEFAULT_CANDIDATE_ID : null)
  const selectedChatId =
    parsed.chatId ?? (currentPage === 'sub-chat' ? DEMO_DEFAULT_CHAT_ID : null)
  
  // 从 URL 或状态获取 caseId
  const selectedCaseId = searchParams.get('caseId') || null

  // 从 URL 获取 counterpartId
  const selectedCounterpartId = searchParams.get('counterpartId') || null

  // 从 URL 解析 caseId 和 viewType
  const urlCaseId = searchParams.get('caseId')
  const urlViewType = searchParams.get('viewType') as 'delayed' | 'matched' | 'interest' | 'candidate' | null

  // 合并 selectedCandidate 和 URL 参数（URL 参数优先）
  const resolvedCandidate: CandidatePreview | null = useMemo(() => {
    if (!selectedCandidate && !urlCaseId && !urlViewType) return null
    return {
      ...(selectedCandidate || {}),
      caseId: urlCaseId ?? selectedCandidate?.caseId,
      viewType: urlViewType ?? selectedCandidate?.viewType,
    } as CandidatePreview
  }, [selectedCandidate, urlCaseId, urlViewType])

  useEffect(() => {
    const sessionFromUrl = searchParams.get('session')
    if (sessionFromUrl) {
      setDiscoverySessionId(sessionFromUrl)
    }
  }, [searchParams])

  const pushPage = useCallback(
    (page: AppPage, params?: {
      candidateId?: string
      chatId?: string
      sessionId?: string | null
      caseId?: string
      viewType?: 'delayed' | 'matched' | 'interest' | 'candidate'
      chatTitle?: string
      counterpartId?: string
    }) => {
      const href = pageToPath(page, {
        candidateId: params?.candidateId,
        chatId: params?.chatId,
        caseId: params?.caseId,
        viewType: params?.viewType,
        chatTitle: params?.chatTitle,
        counterpartId: params?.counterpartId,
      })
      // session 已经在 pageToPath 中处理了，但这里需要额外处理 sessionId
      if (params?.sessionId && page === 'sub-candidate-detail') {
        // 需要合并 session 参数
        const separator = href.includes('?') ? '&' : '?'
        router.push(href + separator + `session=${encodeURIComponent(params.sessionId)}`)
      } else {
        router.push(href)
      }
    },
    [router],
  )

  const handleNavigate = useCallback(
    (page: AppPage) => {
      pushPage(page, {
        candidateId: selectedCandidateId ?? undefined,
        chatId: selectedChatId ?? undefined,
      })
    },
    [pushPage, selectedCandidateId, selectedChatId],
  )

  const handleTabChange = useCallback(
    (tab: TabType) => {
      if (tab === 'matchmaker') pushPage('main-matchmaker')
      if (tab === 'relationships') pushPage('main-relationships')
      if (tab === 'profile') pushPage('main-profile')
    },
    [pushPage],
  )

  const handleViewCandidate = useCallback(
    (candidateId: string, candidate?: CandidatePreview, sessionId?: string | null) => {
      // DEBUG: 调试参数接收
      console.log('[useAppRouter] handleViewCandidate 接收到:', {
        candidateId,
        candidate: candidate ? {
          id: candidate.id,
          caseId: candidate.caseId,
          viewType: candidate.viewType,
        } : null,
        sessionId,
      })
      setSelectedCandidate(candidate || null)
      if (sessionId !== undefined) {
        setDiscoverySessionId(sessionId)
      }
      pushPage('sub-candidate-detail', {
        candidateId,
        sessionId: sessionId ?? discoverySessionId,
        caseId: candidate?.caseId,
        viewType: candidate?.viewType,
      })
    },
    [discoverySessionId, pushPage],
  )

  const handleOpenChat = useCallback(
    (chatId: string, info?: ChatUserInfo) => {
      console.log('[handleOpenChat] 调用参数:', { chatId, info })
      // 使用 URL 参数传递 chatTitle、caseId 和 counterpartId
      pushPage('sub-chat', { chatId, chatTitle: info?.title, caseId: info?.caseId, counterpartId: info?.counterpartId })
    },
    [pushPage],
  )

  const handleOpenInbox = useCallback(() => {
    pushPage('sub-recommendation-inbox')
  }, [pushPage])

  const handleBackToMain = useCallback(() => {
    pushPage(`main-${currentTab}` as AppPage)
  }, [currentTab, pushPage])

  const handleStartVerification = useCallback(
    (from?: 'trust-center') => {
      let href = pageToPath('sub-verification')
      if (from === 'trust-center') {
        href += '?from=trust'
      }
      router.push(href)
    },
    [router],
  )

  const handleBackFromVerification = useCallback(() => {
    if (searchParams.get('from') === 'trust') {
      pushPage('sub-trust-center')
      return
    }
    pushPage(`main-${currentTab}` as AppPage)
  }, [currentTab, pushPage, searchParams])

  const handleOpenTrustCenter = useCallback(() => {
    pushPage('sub-trust-center')
  }, [pushPage])

  const handleOpenCollectedPreferences = useCallback(() => {
    pushPage('sub-collected-preferences')
  }, [pushPage])

  return {
    currentPage,
    currentTab,
    subView,
    selectedCandidateId,
    selectedCandidate: resolvedCandidate,
    selectedChatId,
    selectedCaseId,
    selectedCounterpartId,
    discoverySessionId,
    setDiscoverySessionId,
    handleNavigate,
    handleTabChange,
    handleViewCandidate,
    handleOpenChat,
    handleOpenInbox,
    handleBackToMain,
    handleStartVerification,
    handleBackFromVerification,
    handleOpenTrustCenter,
    handleOpenCollectedPreferences,
  }
}
