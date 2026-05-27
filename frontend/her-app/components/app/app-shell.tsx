'use client'

import { useBadgeCounts } from '@/hooks/use-badge-counts'
import BottomNav from '@/components/her/bottom-nav'
import CandidateDetailPage from '@/components/her/candidate-detail-page'
import ChatPage from '@/components/her/chat-page'
import DiscoverPage, { RecommendationInbox } from '@/components/her/discover-page'
import CollectedPreferencesPage from '@/components/her/collected-preferences-page'
import ProfilePage from '@/components/her/profile-page'
import RelationshipsPage from '@/components/her/relationships-page'
import TrustCenterPage from '@/components/her/trust-center-page'
import VerificationFlowPage from '@/components/her/verification-flow-page'
import { PageTransition, SlideInTransition } from '@/components/her/ui/page-transitions'
import type { CandidatePreview } from '@/lib/types/candidate'
import { DEMO_DEFAULT_CHAT_ID } from '@/lib/navigation/defaults'
import { cn } from '@/lib/utils'
import type { SubView, TabType } from '@/lib/navigation/types'

type AppShellProps = {
  currentTab: TabType
  subView: SubView
  selectedCandidateId: string | null
  selectedCandidate: CandidatePreview | null
  selectedChatId: string | null
  discoverySessionId: string | null
  onDiscoverySessionId: (sessionId: string | null) => void
  onTabChange: (tab: TabType) => void
  onViewCandidate: (candidateId: string, candidate?: CandidatePreview) => void
  onOpenInbox: () => void
  onOpenChat: (chatId: string) => void
  onBackToMain: () => void
  onStartVerification: (from?: 'trust-center') => void
  onBackFromVerification: () => void
  onOpenTrustCenter: () => void
  onOpenCollectedPreferences: () => void
  onOpenOnboarding?: () => void
}

export function AppShell({
  currentTab,
  subView,
  selectedCandidateId,
  selectedCandidate,
  selectedChatId,
  discoverySessionId,
  onDiscoverySessionId,
  onTabChange,
  onViewCandidate,
  onOpenInbox,
  onOpenChat,
  onBackToMain,
  onStartVerification,
  onBackFromVerification,
  onOpenTrustCenter,
  onOpenCollectedPreferences,
  onOpenOnboarding,
}: AppShellProps) {
  const { inboxUnreadCount, relationshipsBadge, refreshBadges } = useBadgeCounts()
  const isMatchmakerMain = currentTab === 'matchmaker' && subView === 'main'

  return (
    <div className="flex h-dvh max-h-dvh w-full max-w-md mx-auto flex-col relative overflow-hidden bg-background">
      <div className="absolute inset-0 bg-gradient-to-b from-rose-soft/30 via-background to-background pointer-events-none" />
      <main
        className={cn(
          'relative z-10 min-h-0',
          isMatchmakerMain
            ? 'flex flex-1 flex-col overflow-hidden'
            : 'flex-1 overflow-y-auto pb-24',
        )}
      >
        {isMatchmakerMain && (
          <PageTransition
            key="matchmaker-main"
            className="flex h-full min-h-0 flex-1 flex-col overflow-hidden"
          >
            <DiscoverPage
              onViewCandidate={(id, candidate) => onViewCandidate(id, candidate)}
              onOpenInbox={onOpenInbox}
              inboxUnreadCount={inboxUnreadCount}
              onSessionIdChange={onDiscoverySessionId}
            />
          </PageTransition>
        )}
        {currentTab === 'matchmaker' && subView === 'recommendation-inbox' && (
          <SlideInTransition key="inbox" direction="right">
            <RecommendationInbox
              onViewCandidate={onViewCandidate}
              onBack={onBackToMain}
              onBadgesRefresh={refreshBadges}
            />
          </SlideInTransition>
        )}

        {currentTab === 'relationships' && subView === 'main' && (
          <PageTransition key="relationships-main">
            <RelationshipsPage
              onOpenChat={onOpenChat}
              onStartVerification={onStartVerification}
            />
          </PageTransition>
        )}

        {currentTab === 'profile' && subView === 'main' && (
          <PageTransition key="profile-main">
            <ProfilePage
              onStartVerification={onStartVerification}
              onOpenTrustCenter={onOpenTrustCenter}
              onOpenCollectedPreferences={onOpenCollectedPreferences}
              onOpenOnboarding={onOpenOnboarding}
            />
          </PageTransition>
        )}

        {subView === 'candidate-detail' && selectedCandidateId && (
          <SlideInTransition key="candidate-detail" direction="right">
            <CandidateDetailPage
              candidateId={selectedCandidateId}
              candidate={selectedCandidate || undefined}
              sessionId={discoverySessionId}
              onBack={onBackToMain}
            />
          </SlideInTransition>
        )}
        {subView === 'chat' && selectedChatId && (
          <SlideInTransition key="chat" direction="right">
            <ChatPage chatId={selectedChatId} onBack={onBackToMain} />
          </SlideInTransition>
        )}
        {subView === 'verification' && (
          <SlideInTransition key="verification" direction="up">
            <VerificationFlowPage onBack={onBackFromVerification} />
          </SlideInTransition>
        )}
        {subView === 'collected-preferences' && (
          <SlideInTransition key="collected-preferences" direction="right">
            <CollectedPreferencesPage onBack={onBackToMain} />
          </SlideInTransition>
        )}
        {subView === 'trust-center' && (
          <SlideInTransition key="trust-center" direction="right">
            <TrustCenterPage
              onStartVerification={() => onStartVerification('trust-center')}
            />
          </SlideInTransition>
        )}
      </main>

      {subView === 'main' && (
        <BottomNav
          currentTab={currentTab}
          onTabChange={onTabChange}
          matchmakerBadge={inboxUnreadCount}
          relationshipsBadge={relationshipsBadge}
        />
      )}
    </div>
  )
}
