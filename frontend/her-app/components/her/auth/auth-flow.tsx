'use client'

import { useState } from 'react'
import WelcomePage from './welcome-page'
import OneClickLoginPage from './one-click-login-page'
import PhoneLoginPage from './phone-login-page'
import VerificationCodePage from './verification-code-page'
import WeChatBindingPage from './wechat-binding-page'
import NewUserWelcomePage from './new-user-welcome-page'
import OnboardingPage from './onboarding-page'
import AccountRecoveryPage from './account-recovery-page'

type AuthView = 
  | 'welcome'
  | 'one-click-login'
  | 'phone-login'
  | 'verification-code'
  | 'wechat-binding'
  | 'new-user-welcome'
  | 'onboarding'
  | 'account-recovery'

interface AuthFlowProps {
  onAuthComplete: () => void
}

export default function AuthFlow({ onAuthComplete }: AuthFlowProps) {
  const [currentView, setCurrentView] = useState<AuthView>('welcome')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [isNewUser, setIsNewUser] = useState(false)

  // Simulate checking if user is new or existing
  const checkUserStatus = () => {
    // In real app, this would be an API call
    return Math.random() > 0.5
  }

  const handleOneClickLogin = () => {
    setCurrentView('one-click-login')
  }

  const handleWeChatLogin = () => {
    // Simulate WeChat auth success
    setTimeout(() => {
      setCurrentView('wechat-binding')
    }, 500)
  }

  const handlePhoneLogin = () => {
    setCurrentView('phone-login')
  }

  const handlePhoneSubmit = (phone: string) => {
    setPhoneNumber(phone)
    setCurrentView('verification-code')
  }

  const handleVerificationSuccess = () => {
    const newUser = checkUserStatus()
    setIsNewUser(newUser)
    
    if (newUser) {
      setCurrentView('new-user-welcome')
    } else {
      onAuthComplete()
    }
  }

  const handleOneClickLoginSuccess = () => {
    const newUser = checkUserStatus()
    setIsNewUser(newUser)
    
    if (newUser) {
      setCurrentView('new-user-welcome')
    } else {
      onAuthComplete()
    }
  }

  const handleWeChatBindPhone = () => {
    setCurrentView('phone-login')
  }

  const handleWeChatSkip = () => {
    setCurrentView('new-user-welcome')
  }

  const handleStartProfile = () => {
    setCurrentView('onboarding')
  }

  const handleOnboardingComplete = () => {
    onAuthComplete()
  }

  const handleAccountRecovery = () => {
    setCurrentView('account-recovery')
  }

  switch (currentView) {
    case 'welcome':
      return (
        <WelcomePage
          onOneClickLogin={handleOneClickLogin}
          onWeChatLogin={handleWeChatLogin}
          onPhoneLogin={handlePhoneLogin}
        />
      )

    case 'one-click-login':
      return (
        <OneClickLoginPage
          phoneNumber="138****1234"
          onLogin={handleOneClickLoginSuccess}
          onUseOtherPhone={handlePhoneLogin}
          onBack={() => setCurrentView('welcome')}
        />
      )

    case 'phone-login':
      return (
        <PhoneLoginPage
          onSubmit={handlePhoneSubmit}
          onWeChatLogin={handleWeChatLogin}
          onBack={() => setCurrentView('welcome')}
        />
      )

    case 'verification-code':
      return (
        <VerificationCodePage
          phone={phoneNumber}
          onVerify={handleVerificationSuccess}
          onResend={() => {}}
          onBack={() => setCurrentView('phone-login')}
        />
      )

    case 'wechat-binding':
      return (
        <WeChatBindingPage
          wechatNickname="微信用户"
          onBindPhone={handleWeChatBindPhone}
          onSkip={handleWeChatSkip}
          onBack={() => setCurrentView('welcome')}
        />
      )

    case 'new-user-welcome':
      return (
        <NewUserWelcomePage
          onStartProfile={handleStartProfile}
        />
      )

    case 'onboarding':
      return (
        <OnboardingPage
          onComplete={handleOnboardingComplete}
          onBack={() => setCurrentView('new-user-welcome')}
        />
      )

    case 'account-recovery':
      return (
        <AccountRecoveryPage
          onVerifyComplete={onAuthComplete}
          onBack={() => setCurrentView('welcome')}
        />
      )

    default:
      return null
  }
}
