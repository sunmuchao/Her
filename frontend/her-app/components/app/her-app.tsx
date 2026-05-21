'use client'

import { DemoNav } from '@/components/app/demo-nav'
import { AppShell } from '@/components/app/app-shell'
import SplashScreen from '@/components/her/splash-screen'
import WelcomePage from '@/components/her/auth/welcome-page'
import PhoneLoginPage from '@/components/her/auth/phone-login-page'
import VerificationCodePage from '@/components/her/auth/verification-code-page'
import WechatBindingPage from '@/components/her/auth/wechat-binding-page'
import NewUserWelcomePage from '@/components/her/auth/new-user-welcome-page'
import OnboardingPage from '@/components/her/auth/onboarding-page'
import AccountRecoveryPage from '@/components/her/auth/account-recovery-page'
import { useAuthFlow } from '@/hooks/use-auth-flow'
import { useAppRouter } from '@/hooks/use-app-router'
import { isDemoNavEnabled } from '@/lib/env'
import type { AppPage } from '@/lib/navigation/types'

function isMainShellPage(page: AppPage): boolean {
  return (
    page === 'main-matchmaker' ||
    page === 'main-relationships' ||
    page === 'main-profile' ||
    page.startsWith('sub-')
  )
}

export function HerApp() {
  const nav = useAppRouter()
  const auth = useAuthFlow(nav.handleNavigate)

  const handleNavigate = (page: AppPage) => {
    if (page === 'auth-welcome') {
      auth.resetAuthOnWelcome()
    }
    nav.handleNavigate(page)
  }

  const renderPage = () => {
    switch (nav.currentPage) {
      case 'splash':
        return <SplashScreen onComplete={() => handleNavigate('auth-welcome')} />

      case 'auth-welcome':
        return (
          <WelcomePage
            maskedPhoneNumber={auth.oneTapAttempt?.maskedPhone || '138****8000'}
            onOneClickLogin={async () => {
              // If no one-tap attempt exists, create one first then verify
              if (!auth.oneTapAttempt) {
                await auth.startOneTapLogin()
              }
              await auth.verifyOneTapLogin()
            }}
            onWeChatLogin={auth.startWechatLogin}
            onPhoneLogin={() => {
              auth.setAuthMode('sms-login')
              handleNavigate('auth-phone')
            }}
            onAccountRecovery={() => handleNavigate('auth-recovery')}
          />
        )
      case 'auth-one-click':
        // Redirect to welcome page since one-click is now merged
        handleNavigate('auth-welcome')
        return null
      case 'auth-phone':
        return (
          <PhoneLoginPage
            onSubmit={auth.requestSmsCode}
            onWeChatLogin={auth.startWechatLogin}
            onBack={() => handleNavigate('auth-welcome')}
          />
        )
      case 'auth-verification-code':
        return (
          <VerificationCodePage
            phone={
              auth.authPhone ||
              (typeof window !== 'undefined'
                ? window.sessionStorage.getItem('her_pending_auth_phone')
                : '') ||
              ''
            }
            onVerify={auth.verifySms}
            onResend={auth.resendSmsCode}
            onBack={() => handleNavigate('auth-phone')}
          />
        )
      case 'auth-wechat-binding':
        return (
          <WechatBindingPage
            wechatNickname={auth.wechatProfile?.nickname || '微信用户'}
            wechatAvatar={auth.wechatProfile?.avatar_url}
            onBindPhone={() => {
              auth.setAuthMode('wechat-bind')
              handleNavigate('auth-phone')
            }}
            onSkip={() => handleNavigate('main-matchmaker')}
            onBack={() => handleNavigate('auth-welcome')}
          />
        )
      case 'auth-new-user-welcome':
        return (
          <NewUserWelcomePage onStartProfile={() => handleNavigate('auth-onboarding')} />
        )
      case 'auth-onboarding':
        return (
          <OnboardingPage
            onComplete={() => handleNavigate('main-matchmaker')}
            onBack={() => handleNavigate('auth-new-user-welcome')}
          />
        )
      case 'auth-recovery':
        return (
          <AccountRecoveryPage
            onVerifyComplete={() => handleNavigate('main-matchmaker')}
            onBack={() => handleNavigate('auth-welcome')}
          />
        )

      default:
        if (isMainShellPage(nav.currentPage)) {
          return (
            <AppShell
              currentTab={nav.currentTab}
              subView={nav.subView}
              selectedCandidateId={nav.selectedCandidateId}
              selectedCandidate={nav.selectedCandidate}
              selectedChatId={nav.selectedChatId}
              discoverySessionId={nav.discoverySessionId}
              onDiscoverySessionId={nav.setDiscoverySessionId}
              onTabChange={nav.handleTabChange}
              onViewCandidate={(id, c) =>
                nav.handleViewCandidate(id, c, nav.discoverySessionId)
              }
              onOpenInbox={nav.handleOpenInbox}
              onOpenChat={nav.handleOpenChat}
              onBackToMain={nav.handleBackToMain}
              onStartVerification={nav.handleStartVerification}
              onBackFromVerification={nav.handleBackFromVerification}
              onOpenTrustCenter={nav.handleOpenTrustCenter}
            />
          )
        }
        return <SplashScreen onComplete={() => handleNavigate('auth-welcome')} />
    }
  }

  return (
    <div className="relative">
      {renderPage()}
      {isDemoNavEnabled() && (
        <DemoNav currentPage={nav.currentPage} onNavigate={handleNavigate} />
      )}
    </div>
  )
}
