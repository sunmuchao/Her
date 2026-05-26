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

  const selectedCandidateId =
    parsed.candidateId ??
    (currentPage === 'sub-candidate-detail' ? DEMO_DEFAULT_CANDIDATE_ID : null)
  const selectedChatId =
    parsed.chatId ?? (currentPage === 'sub-chat' ? DEMO_DEFAULT_CHAT_ID : null)

  useEffect(() => {
    const sessionFromUrl = searchParams.get('session')
    if (sessionFromUrl) {
      setDiscoverySessionId(sessionFromUrl)
    }
  }, [searchParams])

  const pushPage = useCallback(
    (page: AppPage, params?: { candidateId?: string; chatId?: string; sessionId?: string | null }) => {
      let href = pageToPath(page, {
        candidateId: params?.candidateId,
        chatId: params?.chatId,
      })
      if (params?.sessionId && page === 'sub-candidate-detail') {
        href += `?session=${encodeURIComponent(params.sessionId)}`
      }
      router.push(href)
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
      setSelectedCandidate(candidate || null)
      if (sessionId !== undefined) {
        setDiscoverySessionId(sessionId)
      }
      pushPage('sub-candidate-detail', {
        candidateId,
        sessionId: sessionId ?? discoverySessionId,
      })
    },
    [discoverySessionId, pushPage],
  )

  const handleOpenChat = useCallback(
    (chatId: string) => {
      pushPage('sub-chat', { chatId })
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
    selectedCandidate,
    selectedChatId,
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
