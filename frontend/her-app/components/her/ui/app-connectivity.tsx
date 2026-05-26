'use client'

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

type ConnectivityState = {
  online: boolean
  wasOffline: boolean
  markOnline: () => void
}

const ConnectivityContext = createContext<ConnectivityState | null>(null)

export function AppConnectivityProvider({ children }: { children: React.ReactNode }) {
  const [online, setOnline] = useState(true)
  const [wasOffline, setWasOffline] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined') return
    const sync = () => {
      const next = navigator.onLine
      setOnline(next)
      if (!next) setWasOffline(true)
    }
    sync()
    window.addEventListener('online', sync)
    window.addEventListener('offline', sync)
    return () => {
      window.removeEventListener('online', sync)
      window.removeEventListener('offline', sync)
    }
  }, [])

  const markOnline = useCallback(() => {
    setWasOffline(false)
  }, [])

  const value = useMemo(
    () => ({ online, wasOffline, markOnline }),
    [online, wasOffline, markOnline],
  )

  return <ConnectivityContext.Provider value={value}>{children}</ConnectivityContext.Provider>
}

function useAppConnectivity(): ConnectivityState {
  const ctx = useContext(ConnectivityContext)
  if (!ctx) {
    return {
      online: true,
      wasOffline: false,
      markOnline: () => undefined,
    }
  }
  return ctx
}

export function OfflineBanner() {
  const { online } = useAppConnectivity()
  if (online) return null
  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed inset-x-0 top-0 z-50 bg-amber-600 px-4 py-2 text-center text-sm text-white"
    >
      当前网络不可用，部分功能可能无法加载。恢复网络后将自动重试。
    </div>
  )
}
