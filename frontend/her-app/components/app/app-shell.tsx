'use client'

import { useRouter } from 'next/navigation'
import { useBadgeCounts } from '@/hooks/use-badge-counts'
import { useGlobalSSE } from '@/hooks/use-global-sse'
import BottomNav from '@/components/her/bottom-nav'
import CandidateDetailPage from '@/components/her/candidate-detail-page'
import ChatPage from '@/components/her/chat-page'
import DiscoverPage from '@/components/her/discover-page'
import CollectedPreferencesPage from '@/components/her/collected-preferences-page'
import EditProfilePage from '@/components/her/edit-profile-page'
import ProfilePage from '@/components/her/profile-page'
import RelationshipsPage from '@/components/her/relationships-page'
import VerificationFlowPage from '@/components/her/verification'
import SettingsPage from '@/components/her/settings-page'
import { PageTransition, SlideInTransition } from '@/components/her/ui/page-transitions'
import type { CandidatePreview } from '@/lib/types/candidate'
import type { ChatUserInfo } from '@/hooks/use-app-router'
import { cn } from '@/lib/utils'
import type { SubView, TabType } from '@/lib/navigation/types'

type AppShellProps = {
  currentTab: TabType
  subView: SubView
  selectedCandidateId: string | null
  selectedCandidate: CandidatePreview | null
  selectedChatId: string | null
  selectedCaseId: string | null
  selectedCounterpartId: string | null
  fromChatId: string | null
  discoverySessionId: string | null
  onDiscoverySessionId: (sessionId: string | null) => void
  onTabChange: (tab: TabType) => void
  onViewCandidate: (candidateId: string, candidate?: CandidatePreview, sessionId?: string | null, fromChatId?: string) => void
  onOpenChat: (chatId: string, info?: ChatUserInfo) => void
  onBackToMain: () => void
  onStartVerification: (from?: 'profile', target?: string) => void
  onBackFromVerification: () => void
  onOpenCollectedPreferences: () => void
  onOpenEditProfile: () => void
  onOpenSettings: () => void
  onOpenOnboarding?: () => void
  fromSubPage?: string | null
  inboxFilter?: string | null
}

export function AppShell({
  currentTab,
  subView,
  selectedCandidateId,
  selectedCandidate,
  selectedChatId,
  selectedCaseId,
  selectedCounterpartId,
  fromChatId,
  discoverySessionId,
  onDiscoverySessionId,
  onTabChange,
  onViewCandidate,
  onOpenChat,
  onBackToMain,
  onStartVerification,
  onBackFromVerification,
  onOpenCollectedPreferences: _onOpenCollectedPreferences,
  onOpenEditProfile,
  onOpenSettings,
  onOpenOnboarding,
  fromSubPage,
  inboxFilter,
}: AppShellProps) {
  console.log('[AppShell] 开始渲染')
  console.log('[AppShell] props:', { currentTab, subView, selectedCandidateId, selectedChatId })

  const router = useRouter()
  const { inboxUnreadCount, relationshipsBadge, refreshBadges } = useBadgeCounts()
  const { isConnected: sseConnected } = useGlobalSSE() // ✅ 新增：全局SSE订阅
  const isMatchmakerMain = currentTab === 'matchmaker' && subView === 'main'
  const isFullscreenSubView = subView === 'chat'

  return (
    <div className="flex h-dvh max-h-dvh w-full max-w-md mx-auto flex-col relative overflow-hidden bg-background">
      <div className="absolute inset-0 bg-gradient-to-b from-rose-soft/30 via-background to-background pointer-events-none" />
      <main
        className={cn(
          'relative z-10 min-h-0',
          isMatchmakerMain
            ? 'flex flex-1 flex-col overflow-hidden'
            : isFullscreenSubView
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
              onViewCandidate={(id, candidate, sessionId) => onViewCandidate(id, candidate, sessionId)}
              onSessionIdChange={onDiscoverySessionId}
            />
          </PageTransition>
        )}

        {currentTab === 'relationships' && subView === 'main' && (
          <PageTransition key="relationships-main">
            <RelationshipsPage
              onOpenChat={onOpenChat}
              onNavigateToDiscover={() => onTabChange('matchmaker')}
              onViewCandidate={onViewCandidate}
            />
          </PageTransition>
        )}

        {currentTab === 'profile' && subView === 'main' && (
          <PageTransition key="profile-main">
            <ProfilePage
              onStartVerification={onStartVerification}
              onOpenOnboarding={onOpenOnboarding}
              onOpenEditProfile={onOpenEditProfile}
              onOpenSettings={onOpenSettings}
            />
          </PageTransition>
        )}

        {subView === 'candidate-detail' && selectedCandidateId && (
          <SlideInTransition key="candidate-detail" direction="right">
            <CandidateDetailPage
              candidateId={selectedCandidateId}
              candidate={selectedCandidate || undefined}
              sessionId={discoverySessionId}
              caseId={selectedCandidate?.caseId}
              viewType={selectedCandidate?.viewType}
              onBack={() => {
                // 如果有 fromChatId，返回时回到聊天页面
                if (fromChatId) {
                  onOpenChat(fromChatId, {
                    caseId: selectedCaseId || undefined,
                    counterpartId: selectedCounterpartId || undefined,
                  })
                } else {
                  onBackToMain()
                }
              }}
              onOpenRelationships={() => {
                onTabChange('relationships')
              }}
            />
          </SlideInTransition>
        )}
        {subView === 'chat' && selectedChatId && (
          <SlideInTransition key="chat" direction="right" className="flex h-full min-h-0 flex-1 flex-col overflow-hidden">
            <ChatPage
              chatId={selectedChatId}
              caseId={selectedCaseId}
              counterpartId={selectedCounterpartId}
              onBack={onBackToMain}
              onViewCandidate={onViewCandidate}
            />
          </SlideInTransition>
        )}
        {subView === 'verification' && (
          <SlideInTransition key="verification" direction="up">
            <VerificationFlowPage onBack={onBackFromVerification} />
          </SlideInTransition>
        )}
        {subView === 'collected-preferences' && (
          <SlideInTransition key="collected-preferences" direction="right">
            <CollectedPreferencesPage onBack={() => router.back()} />
          </SlideInTransition>
        )}
        {subView === 'edit-profile' && (
          <SlideInTransition key="edit-profile" direction="right">
            <EditProfilePage
              onBack={() => router.back()}
              onSaved={() => router.back()}
            />
          </SlideInTransition>
        )}
        {subView === 'settings' && (
          <SlideInTransition key="settings" direction="right">
            <SettingsPage
              onBack={() => router.back()}
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
