'use client'

import { useState } from 'react'
import { Menu, X, Sparkles, User, Shield, MessageCircle, Heart, Search, CheckCircle, LogIn, Phone, KeyRound, Link2, UserPlus, ClipboardList, RotateCcw, Mail } from 'lucide-react'
import SplashScreen from '@/components/her/splash-screen'
import BottomNav from '@/components/her/bottom-nav'
import DiscoverPage, { RecommendationInbox } from '@/components/her/discover-page'
import RelationshipsPage from '@/components/her/relationships-page'
import ProfilePage from '@/components/her/profile-page'
import CandidateDetailPage from '@/components/her/candidate-detail-page'
import ChatPage from '@/components/her/chat-page'
import VerificationFlowPage from '@/components/her/verification-flow-page'
import TrustCenterPage from '@/components/her/trust-center-page'

// Auth pages
import WelcomePage from '@/components/her/auth/welcome-page'
import OneClickLoginPage from '@/components/her/auth/one-click-login-page'
import PhoneLoginPage from '@/components/her/auth/phone-login-page'
import VerificationCodePage from '@/components/her/auth/verification-code-page'
import WechatBindingPage from '@/components/her/auth/wechat-binding-page'
import NewUserWelcomePage from '@/components/her/auth/new-user-welcome-page'
import OnboardingPage from '@/components/her/auth/onboarding-page'
import AccountRecoveryPage from '@/components/her/auth/account-recovery-page'
import { PageTransition, SlideInTransition } from '@/components/her/ui/page-transitions'

// 3-Tab Navigation: 红娘 | 关系 | 我的
export type TabType = 'matchmaker' | 'relationships' | 'profile'

// Sub-views for each tab
type SubView = 'main' | 'recommendation-inbox' | 'candidate-detail' | 'chat' | 'verification' | 'trust-center'

type DemoPage = 
  | 'splash'
  | 'auth-welcome'
  | 'auth-one-click'
  | 'auth-phone'
  | 'auth-verification-code'
  | 'auth-wechat-binding'
  | 'auth-new-user-welcome'
  | 'auth-onboarding'
  | 'auth-recovery'
  | 'main-matchmaker'
  | 'main-relationships'
  | 'main-profile'
  | 'sub-recommendation-inbox'
  | 'sub-candidate-detail'
  | 'sub-chat'
  | 'sub-verification'
  | 'sub-trust-center'

const pageCategories = [
  {
    name: '启动 & 账户',
    pages: [
      { id: 'splash' as DemoPage, name: '启动页', icon: Sparkles },
      { id: 'auth-welcome' as DemoPage, name: '欢迎页', icon: LogIn },
      { id: 'auth-one-click' as DemoPage, name: '一键登录', icon: User },
      { id: 'auth-phone' as DemoPage, name: '手机号登录', icon: Phone },
      { id: 'auth-verification-code' as DemoPage, name: '验证码', icon: KeyRound },
      { id: 'auth-wechat-binding' as DemoPage, name: '微信绑定', icon: Link2 },
      { id: 'auth-new-user-welcome' as DemoPage, name: '新用户欢迎', icon: UserPlus },
      { id: 'auth-onboarding' as DemoPage, name: '资料填写', icon: ClipboardList },
      { id: 'auth-recovery' as DemoPage, name: '账号找回', icon: RotateCcw },
    ]
  },
  {
    name: '主功能 (3 Tab)',
    pages: [
      { id: 'main-matchmaker' as DemoPage, name: '红娘', icon: Sparkles },
      { id: 'main-relationships' as DemoPage, name: '关系', icon: Heart },
      { id: 'main-profile' as DemoPage, name: '我的', icon: User },
    ]
  },
  {
    name: '二级页面',
    pages: [
      { id: 'sub-recommendation-inbox' as DemoPage, name: '推荐来信', icon: Mail },
      { id: 'sub-candidate-detail' as DemoPage, name: '候选人详情', icon: User },
      { id: 'sub-chat' as DemoPage, name: '聊天', icon: MessageCircle },
      { id: 'sub-verification' as DemoPage, name: '认证流程', icon: CheckCircle },
      { id: 'sub-trust-center' as DemoPage, name: '认证中心', icon: Shield },
    ]
  }
]

export default function HerApp() {
  const [currentPage, setCurrentPage] = useState<DemoPage>('splash')
  const [showNav, setShowNav] = useState(false)
  const [currentTab, setCurrentTab] = useState<TabType>('matchmaker')
  const [subView, setSubView] = useState<SubView>('main')
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null)
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null)

  // Mock badge counts
  const inboxUnreadCount = 3
  const chatUnreadCount = 2

  const handleNavigate = (page: DemoPage) => {
    setCurrentPage(page)
    setShowNav(false)
    setSubView('main')
    
    // Sync tab state for main pages
    if (page === 'main-matchmaker') setCurrentTab('matchmaker')
    if (page === 'main-relationships') setCurrentTab('relationships')
    if (page === 'main-profile') setCurrentTab('profile')
    
    // Handle sub-pages
    if (page === 'sub-recommendation-inbox') {
      setCurrentTab('matchmaker')
      setSubView('recommendation-inbox')
    }
    if (page === 'sub-candidate-detail') {
      setSubView('candidate-detail')
      setSelectedCandidateId('demo')
    }
    if (page === 'sub-chat') {
      setCurrentTab('relationships')
      setSubView('chat')
      setSelectedChatId('demo')
    }
    if (page === 'sub-verification') {
      setSubView('verification')
    }
    if (page === 'sub-trust-center') {
      setCurrentTab('profile')
      setSubView('trust-center')
    }
  }

  const handleTabChange = (tab: TabType) => {
    setCurrentTab(tab)
    setSubView('main')
    setCurrentPage(`main-${tab}` as DemoPage)
  }

  const handleViewCandidate = (candidateId: string) => {
    setSelectedCandidateId(candidateId)
    setSubView('candidate-detail')
    setCurrentPage('sub-candidate-detail')
  }

  const handleOpenChat = (chatId?: string) => {
    setSelectedChatId(chatId || 'demo')
    setSubView('chat')
    setCurrentPage('sub-chat')
  }

  const handleOpenInbox = () => {
    setSubView('recommendation-inbox')
    setCurrentPage('sub-recommendation-inbox')
  }

  const handleBackToMain = () => {
    setSubView('main')
    setCurrentPage(`main-${currentTab}` as DemoPage)
  }

  const handleStartVerification = () => {
    setSubView('verification')
    setCurrentPage('sub-verification')
  }

  const handleOpenTrustCenter = () => {
    setSubView('trust-center')
    setCurrentPage('sub-trust-center')
  }

  const renderPage = () => {
    switch (currentPage) {
      // Splash
      case 'splash':
        return <SplashScreen onComplete={() => handleNavigate('auth-welcome')} />
      
      // Auth pages
      case 'auth-welcome':
        return <WelcomePage 
          onOneClickLogin={() => handleNavigate('auth-one-click')}
          onWeChatLogin={() => handleNavigate('auth-wechat-binding')}
          onPhoneLogin={() => handleNavigate('auth-phone')}
        />
      case 'auth-one-click':
        return <OneClickLoginPage 
          onLogin={() => handleNavigate('main-matchmaker')}
          onUseOtherPhone={() => handleNavigate('auth-phone')}
          onBack={() => handleNavigate('auth-welcome')}
        />
      case 'auth-phone':
        return <PhoneLoginPage 
          onSubmit={() => handleNavigate('auth-verification-code')}
          onWeChatLogin={() => handleNavigate('auth-wechat-binding')}
          onBack={() => handleNavigate('auth-welcome')}
        />
      case 'auth-verification-code':
        return <VerificationCodePage 
          phone="13812348888"
          onVerify={() => handleNavigate('auth-new-user-welcome')}
          onResend={() => undefined}
          onBack={() => handleNavigate('auth-phone')}
        />
      case 'auth-wechat-binding':
        return <WechatBindingPage 
          onBindPhone={() => handleNavigate('auth-phone')}
          onSkip={() => handleNavigate('main-matchmaker')}
          onBack={() => handleNavigate('auth-welcome')}
        />
      case 'auth-new-user-welcome':
        return <NewUserWelcomePage 
          onStartProfile={() => handleNavigate('auth-onboarding')}
        />
      case 'auth-onboarding':
        return <OnboardingPage 
          onComplete={() => handleNavigate('main-matchmaker')}
          onBack={() => handleNavigate('auth-new-user-welcome')}
        />
      case 'auth-recovery':
        return <AccountRecoveryPage 
          onVerifyComplete={() => handleNavigate('main-matchmaker')}
          onBack={() => handleNavigate('auth-welcome')}
        />
      
      // Main pages with bottom nav and sub-views
      case 'main-matchmaker':
      case 'main-relationships':
      case 'main-profile':
      case 'sub-recommendation-inbox':
      case 'sub-candidate-detail':
      case 'sub-chat':
      case 'sub-verification':
      case 'sub-trust-center':
        return (
          <div className="min-h-screen bg-background flex flex-col max-w-md mx-auto relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-b from-rose-soft/30 via-background to-background pointer-events-none" />
            <main className="flex-1 overflow-y-auto pb-24 relative z-10">
              {/* Matchmaker Tab */}
              {currentTab === 'matchmaker' && subView === 'main' && (
                <PageTransition key="matchmaker-main">
                  <DiscoverPage 
                    onViewCandidate={handleViewCandidate}
                    onOpenInbox={handleOpenInbox}
                    inboxUnreadCount={inboxUnreadCount}
                  />
                </PageTransition>
              )}
              {currentTab === 'matchmaker' && subView === 'recommendation-inbox' && (
                <SlideInTransition key="inbox" direction="right">
                  <RecommendationInbox 
                    onViewCandidate={handleViewCandidate}
                    onBack={handleBackToMain}
                  />
                </SlideInTransition>
              )}
              
              {/* Relationships Tab */}
              {currentTab === 'relationships' && subView === 'main' && (
                <PageTransition key="relationships-main">
                  <RelationshipsPage 
                    onOpenChat={handleOpenChat}
                    onStartVerification={handleStartVerification}
                  />
                </PageTransition>
              )}
              
              {/* Profile Tab */}
              {currentTab === 'profile' && subView === 'main' && (
                <PageTransition key="profile-main">
                  <ProfilePage 
                    onStartVerification={handleStartVerification}
                    onOpenTrustCenter={handleOpenTrustCenter}
                  />
                </PageTransition>
              )}
              
              {/* Shared Sub-views */}
              {subView === 'candidate-detail' && selectedCandidateId && (
                <SlideInTransition key="candidate-detail" direction="right">
                  <CandidateDetailPage 
                    candidateId={selectedCandidateId} 
                    onBack={handleBackToMain}
                    onStartChat={() => handleOpenChat()}
                  />
                </SlideInTransition>
              )}
              {subView === 'chat' && selectedChatId && (
                <SlideInTransition key="chat" direction="right">
                  <ChatPage 
                    chatId={selectedChatId}
                    onBack={handleBackToMain}
                  />
                </SlideInTransition>
              )}
              {subView === 'verification' && (
                <SlideInTransition key="verification" direction="up">
                  <VerificationFlowPage onBack={handleBackToMain} />
                </SlideInTransition>
              )}
              {subView === 'trust-center' && (
                <SlideInTransition key="trust-center" direction="right">
                  <TrustCenterPage onStartVerification={handleStartVerification} />
                </SlideInTransition>
              )}
            </main>
            
            {/* Only show bottom nav on main views */}
            {subView === 'main' && (
              <BottomNav 
                currentTab={currentTab} 
                onTabChange={handleTabChange}
                matchmakerBadge={inboxUnreadCount}
                relationshipsBadge={chatUnreadCount}
              />
            )}
          </div>
        )
      
      default:
        return <SplashScreen onComplete={() => handleNavigate('auth-welcome')} />
    }
  }

  return (
    <div className="relative">
      {renderPage()}
      
      {/* Demo Navigation Toggle */}
      <button
        onClick={() => setShowNav(!showNav)}
        className="fixed bottom-6 right-6 z-[100] w-14 h-14 rounded-full bg-primary text-primary-foreground shadow-elevated flex items-center justify-center transition-transform hover:scale-105 active:scale-95"
      >
        {showNav ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
      </button>

      {/* Demo Navigation Panel */}
      {showNav && (
        <>
          <div 
            className="fixed inset-0 bg-black/40 z-[90] backdrop-blur-sm"
            onClick={() => setShowNav(false)}
          />
          <div className="fixed bottom-24 right-6 z-[100] w-72 max-h-[70vh] overflow-y-auto bg-card rounded-2xl shadow-elevated border border-border/50">
            <div className="p-4 border-b border-border/50">
              <h3 className="font-serif text-lg text-foreground">页面导航</h3>
              <p className="text-xs text-muted-foreground mt-1">3 Tab 极简导航架构</p>
            </div>
            <div className="p-2">
              {pageCategories.map((category) => (
                <div key={category.name} className="mb-4">
                  <h4 className="text-xs font-medium text-muted-foreground px-2 py-1 uppercase tracking-wider">
                    {category.name}
                  </h4>
                  <div className="space-y-1">
                    {category.pages.map((page) => {
                      const Icon = page.icon
                      const isActive = currentPage === page.id
                      return (
                        <button
                          key={page.id}
                          onClick={() => handleNavigate(page.id)}
                          className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-colors ${
                            isActive 
                              ? 'bg-primary/10 text-primary' 
                              : 'hover:bg-muted/50 text-foreground'
                          }`}
                        >
                          <Icon className="w-4 h-4 flex-shrink-0" />
                          <span className="text-sm">{page.name}</span>
                          {isActive && (
                            <span className="ml-auto w-2 h-2 rounded-full bg-primary" />
                          )}
                        </button>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
