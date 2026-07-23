'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import type { CandidatePreview } from '@/lib/types/candidate'
import { DEMO_DEFAULT_CANDIDATE_ID, DEMO_DEFAULT_CHAT_ID } from '@/lib/navigation/defaults'
import { pageToPath, pathToPage } from '@/lib/navigation/routes'
import type { AppPage, SubView, TabType } from '@/lib/navigation/types'

function pageToTab(page: AppPage): TabType {
  if (page === 'main-relationships' || page === 'sub-chat') return 'relationships'
  if (page === 'main-profile' || page === 'sub-verification' || page === 'sub-collected-preferences' || page === 'sub-edit-profile' || page === 'sub-settings') return 'profile'
  return 'matchmaker'
}

function pageToSubView(page: AppPage): SubView {
  if (page === 'sub-candidate-detail') return 'candidate-detail'
  if (page === 'sub-chat') return 'chat'
  if (page === 'sub-verification') return 'verification'
  if (page === 'sub-collected-preferences') return 'collected-preferences'
  if (page === 'sub-edit-profile') return 'edit-profile'
  if (page === 'sub-settings') return 'settings'
  return 'main'
}

export type ChatUserInfo = {
  title?: string
  avatar?: string
  caseId?: string
  counterpartId?: string
}

// 记录来源 tab，用于详情页返回
let lastSourceTab: TabType | null = null

export function useAppRouter() {
  console.log('[useAppRouter] 开始初始化')

  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  console.log('[useAppRouter] pathname:', pathname)
  console.log('[useAppRouter] searchParams:', searchParams.toString())

  const parsed = useMemo(() => pathToPage(pathname), [pathname])
  const currentPage = parsed.page

  console.log('[useAppRouter] parsed page:', currentPage)

  // 当进入详情页时，使用记录的来源 tab
  const currentTab = currentPage === 'sub-candidate-detail' && lastSourceTab
    ? lastSourceTab
    : pageToTab(currentPage)
  const subView = pageToSubView(currentPage)

  console.log('[useAppRouter] currentTab:', currentTab)
  console.log('[useAppRouter] subView:', subView)

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

  // 从 URL 获取 fromChatId（用于返回时回到聊天页面）
  const fromChatId = searchParams.get('fromChatId') || null

  // 从 URL 获取 fromSubPage 和 inboxFilter（用于推荐来信返回）
  const fromSubPage = searchParams.get('fromSubPage') || null
  const inboxFilter = searchParams.get('inboxFilter') || null

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
      fromChatId?: string
      fromSubPage?: string
      inboxFilter?: string
      from?: 'profile'
      target?: 'video' | 'education' | 'occupation' | 'income'
    }) => {
      const href = pageToPath(page, {
        candidateId: params?.candidateId,
        chatId: params?.chatId,
        caseId: params?.caseId,
        viewType: params?.viewType,
        chatTitle: params?.chatTitle,
        counterpartId: params?.counterpartId,
        fromChatId: params?.fromChatId,
        fromSubPage: params?.fromSubPage,
        inboxFilter: params?.inboxFilter,
        from: params?.from,
        target: params?.target,
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
    (candidateId: string, candidate?: CandidatePreview, sessionId?: string | null, fromChatId?: string) => {
      // DEBUG: 调试参数接收
      console.log('[useAppRouter] handleViewCandidate 接收到:', {
        candidateId,
        candidate: candidate ? {
          id: candidate.id,
          caseId: candidate.caseId,
          viewType: candidate.viewType,
          fromSubPage: candidate.fromSubPage,
          inboxFilter: candidate.inboxFilter,
        } : null,
        sessionId,
        fromChatId,
      })
      // 记录来源 tab，用于详情页返回
      lastSourceTab = currentTab
      setSelectedCandidate(candidate || null)
      if (sessionId !== undefined) {
        setDiscoverySessionId(sessionId)
      }
      pushPage('sub-candidate-detail', {
        candidateId,
        sessionId: sessionId ?? discoverySessionId,
        caseId: candidate?.caseId,
        viewType: candidate?.viewType,
        fromChatId,
        fromSubPage: candidate?.fromSubPage,
        inboxFilter: candidate?.inboxFilter,
      })
    },
    [currentTab, discoverySessionId, pushPage],
  )

  const handleOpenChat = useCallback(
    (chatId: string, info?: ChatUserInfo) => {
      console.log('[handleOpenChat] 调用参数:', { chatId, info })
      // 使用 URL 参数传递 chatTitle、caseId 和 counterpartId
      pushPage('sub-chat', { chatId, chatTitle: info?.title, caseId: info?.caseId, counterpartId: info?.counterpartId })
    },
    [pushPage],
  )

  const handleBackToMain = useCallback(() => {
    pushPage(`main-${currentTab}` as AppPage)
  }, [currentTab, pushPage])

  const handleStartVerification = useCallback(
    (from?: 'profile', target?: string) => {
      pushPage('sub-verification', {
        from: from,
        target: target as 'video' | 'education' | 'occupation' | 'income' | undefined,
      })
    },
    [pushPage],
  )

  const handleBackFromVerification = useCallback(() => {
    if (searchParams.get('from') === 'profile') {
      pushPage('main-profile')
      return
    }
    pushPage(`main-${currentTab}` as AppPage)
  }, [currentTab, pushPage, searchParams])

  const handleOpenCollectedPreferences = useCallback(() => {
    pushPage('sub-collected-preferences')
  }, [pushPage])

  const handleOpenSettings = useCallback(() => {
    pushPage('sub-settings')
  }, [pushPage])

  const handleOpenEditProfile = useCallback(() => {
    pushPage('sub-edit-profile')
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
    fromChatId,
    fromSubPage,
    inboxFilter,
    discoverySessionId,
    setDiscoverySessionId,
    handleNavigate,
    handleTabChange,
    handleViewCandidate,
    handleOpenChat,
    handleBackToMain,
    handleStartVerification,
    handleBackFromVerification,
    handleOpenCollectedPreferences,
    handleOpenEditProfile,
    handleOpenSettings,
  }
}
