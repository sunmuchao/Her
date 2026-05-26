'use client'

import { useEffect } from 'react'
import { hydrateSessionFromAuthMe } from '@/lib/auth/hydrate-session'
import { isOnboardingComplete } from '@/lib/auth/onboarding-gate'
import { getAccessToken } from '@/lib/auth/session'
import type { AppPage } from '@/lib/navigation/types'

function isMainShellPage(page: AppPage): boolean {
  return (
    page === 'main-matchmaker' ||
    page === 'main-relationships' ||
    page === 'main-profile' ||
    page.startsWith('sub-')
  )
}

/** Redirect authenticated users without a linked profile away from main app routes. */
export function useOnboardingGuard(
  currentPage: AppPage,
  onNavigate: (page: AppPage) => void,
) {
  useEffect(() => {
    if (!isMainShellPage(currentPage)) return
    if (!getAccessToken()) return

    let cancelled = false

    void (async () => {
      const authMe = await hydrateSessionFromAuthMe()
      if (cancelled || !authMe) return
      if (!isOnboardingComplete(authMe)) {
        onNavigate('auth-onboarding')
      }
    })()

    return () => {
      cancelled = true
    }
  }, [currentPage, onNavigate])
}
