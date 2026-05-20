'use client'

import { useState } from 'react'
import { useSearchParams } from 'next/navigation'

import SplashScreen from '@/components/her/splash-screen'
import BottomNav from '@/components/her/bottom-nav'
import DiscoverPage from '@/components/her/discover-page'
import RecommendationsPage from '@/components/her/recommendations-page'
import RelationshipsPage from '@/components/her/relationships-page'
import TrustCenterPage from '@/components/her/trust-center-page'
import ProfilePage from '@/components/her/profile-page'
import CandidateDetailPage from '@/components/her/candidate-detail-page'
import ChatPage from '@/components/her/chat-page'
import VerificationFlowPage from '@/components/her/verification-flow-page'
import { envText, parseOptionalInt, type HerRuntimeContext } from '@/lib/runtime-context'

export type TabType = 'discover' | 'recommendations' | 'relationships' | 'trust' | 'profile'
export type ViewType = 'main' | 'candidate-detail' | 'chat' | 'verification'

function buildRuntimeContext(searchParams: URLSearchParams): HerRuntimeContext {
  const requesterId =
    parseOptionalInt(searchParams.get('requester_id')) ??
    parseOptionalInt(process.env.NEXT_PUBLIC_HER_REQUESTER_ID)
  const profileId =
    parseOptionalInt(searchParams.get('profile_id')) ??
    parseOptionalInt(process.env.NEXT_PUBLIC_HER_PROFILE_ID)
  const userId =
    envText(searchParams.get('user_id') || undefined) ||
    envText(process.env.NEXT_PUBLIC_HER_USER_ID) ||
    (requesterId ? String(requesterId) : undefined)
  const caseId =
    envText(searchParams.get('case_id') || undefined) ||
    envText(process.env.NEXT_PUBLIC_HER_CASE_ID)

  return {
    requesterId,
    profileId,
    userId,
    caseId,
  }
}

export default function HerApp() {
  const searchParams = useSearchParams()
  const runtimeContext = buildRuntimeContext(searchParams)

  const [showSplash, setShowSplash] = useState(true)
  const [currentTab, setCurrentTab] = useState<TabType>('discover')
  const [currentView, setCurrentView] = useState<ViewType>('main')
  const [selectedCandidate, setSelectedCandidate] = useState<string | null>(null)
  const [selectedChat, setSelectedChat] = useState<string | null>(null)
  const [discoverySessionId, setDiscoverySessionId] = useState<string | undefined>(undefined)

  if (showSplash) {
    return <SplashScreen onComplete={() => setShowSplash(false)} />
  }

  if (currentView === 'candidate-detail' && selectedCandidate) {
    return (
      <CandidateDetailPage
        candidateId={selectedCandidate}
        sessionId={discoverySessionId}
        runtimeContext={runtimeContext}
        onBack={() => {
          setCurrentView('main')
          setSelectedCandidate(null)
        }}
        onStartChat={(chatId) => {
          setSelectedChat(chatId)
          setCurrentView('chat')
        }}
      />
    )
  }

  if (currentView === 'chat' && selectedChat) {
    return (
      <ChatPage
        conversationId={selectedChat}
        runtimeContext={runtimeContext}
        onBack={() => {
          setCurrentView('main')
          setSelectedChat(null)
        }}
      />
    )
  }

  if (currentView === 'verification') {
    return (
      <VerificationFlowPage
        runtimeContext={runtimeContext}
        onBack={() => setCurrentView('main')}
      />
    )
  }

  return (
    <div className="min-h-screen bg-background flex flex-col max-w-md mx-auto relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-b from-rose-soft/30 via-background to-background pointer-events-none" />
      <main className="flex-1 overflow-y-auto pb-24 relative z-10">
        {currentTab === 'discover' && (
          <DiscoverPage
            runtimeContext={runtimeContext}
            onSessionChange={setDiscoverySessionId}
            onViewCandidate={(candidateId) => {
              setSelectedCandidate(candidateId)
              setCurrentView('candidate-detail')
            }}
          />
        )}
        {currentTab === 'recommendations' && (
          <RecommendationsPage
            runtimeContext={runtimeContext}
            onViewCandidate={(candidateId) => {
              setSelectedCandidate(candidateId)
              setCurrentView('candidate-detail')
            }}
          />
        )}
        {currentTab === 'relationships' && (
          <RelationshipsPage
            runtimeContext={runtimeContext}
            onOpenChat={(conversationId) => {
              setSelectedChat(conversationId)
              setCurrentView('chat')
            }}
            onStartVerification={() => setCurrentView('verification')}
          />
        )}
        {currentTab === 'trust' && (
          <TrustCenterPage
            runtimeContext={runtimeContext}
            onStartVerification={() => setCurrentView('verification')}
          />
        )}
        {currentTab === 'profile' && (
          <ProfilePage
            runtimeContext={runtimeContext}
            onStartVerification={() => setCurrentView('verification')}
          />
        )}
      </main>
      <BottomNav currentTab={currentTab} onTabChange={setCurrentTab} />
    </div>
  )
}
