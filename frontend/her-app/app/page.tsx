'use client'

import { useState } from 'react'
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

export type TabType = 'discover' | 'recommendations' | 'relationships' | 'trust' | 'profile'
export type ViewType = 'main' | 'candidate-detail' | 'chat' | 'verification'

export default function HerApp() {
  const [showSplash, setShowSplash] = useState(true)
  const [currentTab, setCurrentTab] = useState<TabType>('discover')
  const [currentView, setCurrentView] = useState<ViewType>('main')
  const [selectedCandidate, setSelectedCandidate] = useState<string | null>(null)
  const [selectedChat, setSelectedChat] = useState<string | null>(null)

  const handleSplashComplete = () => {
    setShowSplash(false)
  }

  const handleViewCandidate = (candidateId: string) => {
    setSelectedCandidate(candidateId)
    setCurrentView('candidate-detail')
  }

  const handleOpenChat = (chatId: string) => {
    setSelectedChat(chatId)
    setCurrentView('chat')
  }

  const handleStartVerification = () => {
    setCurrentView('verification')
  }

  const handleBack = () => {
    setCurrentView('main')
    setSelectedCandidate(null)
    setSelectedChat(null)
  }

  if (showSplash) {
    return <SplashScreen onComplete={handleSplashComplete} />
  }

  if (currentView === 'candidate-detail' && selectedCandidate) {
    return (
      <CandidateDetailPage 
        candidateId={selectedCandidate} 
        onBack={handleBack}
        onStartChat={handleOpenChat}
      />
    )
  }

  if (currentView === 'chat') {
    return (
      <ChatPage 
        chatId={selectedChat}
        onBack={handleBack}
      />
    )
  }

  if (currentView === 'verification') {
    return (
      <VerificationFlowPage onBack={handleBack} />
    )
  }

  return (
    <div className="min-h-screen bg-background flex flex-col max-w-md mx-auto relative overflow-hidden">
      {/* Subtle background gradient */}
      <div className="absolute inset-0 bg-gradient-to-b from-rose-soft/30 via-background to-background pointer-events-none" />
      
      {/* Main content area */}
      <main className="flex-1 overflow-y-auto pb-24 relative z-10">
        {currentTab === 'discover' && (
          <DiscoverPage onViewCandidate={handleViewCandidate} />
        )}
        {currentTab === 'recommendations' && (
          <RecommendationsPage onViewCandidate={handleViewCandidate} />
        )}
        {currentTab === 'relationships' && (
          <RelationshipsPage 
            onOpenChat={handleOpenChat}
            onStartVerification={handleStartVerification}
          />
        )}
        {currentTab === 'trust' && (
          <TrustCenterPage onStartVerification={handleStartVerification} />
        )}
        {currentTab === 'profile' && (
          <ProfilePage onStartVerification={handleStartVerification} />
        )}
      </main>

      {/* Bottom navigation */}
      <BottomNav currentTab={currentTab} onTabChange={setCurrentTab} />
    </div>
  )
}
