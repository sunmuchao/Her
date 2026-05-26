import { DEMO_DEFAULT_CANDIDATE_ID, DEMO_DEFAULT_CHAT_ID } from '@/lib/navigation/defaults'
import type { AppPage } from '@/lib/navigation/types'

export type RouteParams = {
  candidateId?: string
  chatId?: string
}

export type ParsedRoute = RouteParams & {
  page: AppPage
}

export function pageToPath(page: AppPage, params: RouteParams = {}): string {
  switch (page) {
    case 'splash':
      return '/splash'
    case 'auth-welcome':
      return '/welcome'
    case 'auth-one-click':
      return '/login/one-tap'
    case 'auth-phone':
      return '/login/phone'
    case 'auth-verification-code':
      return '/login/verify'
    case 'auth-wechat-binding':
      return '/wechat/bind'
    case 'auth-new-user-welcome':
      return '/onboarding/welcome'
    case 'auth-onboarding':
      return '/onboarding'
    case 'auth-recovery':
      return '/recovery'
    case 'main-matchmaker':
      return '/discover'
    case 'main-relationships':
      return '/relationships'
    case 'main-profile':
      return '/profile'
    case 'sub-recommendation-inbox':
      return '/inbox'
    case 'sub-candidate-detail':
      return `/candidates/${params.candidateId ?? DEMO_DEFAULT_CANDIDATE_ID}`
    case 'sub-chat':
      return `/chat/${params.chatId ?? DEMO_DEFAULT_CHAT_ID}`
    case 'sub-verification':
      return '/verification'
    case 'sub-trust-center':
      return '/trust'
    case 'sub-collected-preferences':
      return '/profile/collected'
    case 'ops-workbench':
      return '/ops/workbench'
    default:
      return '/splash'
  }
}

export function pathToPage(pathname: string): ParsedRoute {
  const path = pathname.replace(/\/+$/, '') || '/splash'

  if (path === '/' || path === '/splash') return { page: 'splash' }
  if (path === '/welcome') return { page: 'auth-welcome' }
  if (path === '/login/one-tap') return { page: 'auth-one-click' }
  if (path === '/login/phone') return { page: 'auth-phone' }
  if (path === '/login/verify') return { page: 'auth-verification-code' }
  if (path === '/wechat/bind') return { page: 'auth-wechat-binding' }
  if (path === '/onboarding/welcome') return { page: 'auth-new-user-welcome' }
  if (path === '/onboarding') return { page: 'auth-onboarding' }
  if (path === '/recovery') return { page: 'auth-recovery' }
  if (path === '/discover') return { page: 'main-matchmaker' }
  if (path === '/relationships') return { page: 'main-relationships' }
  if (path === '/profile') return { page: 'main-profile' }
  if (path === '/inbox') return { page: 'sub-recommendation-inbox' }
  if (path === '/verification') return { page: 'sub-verification' }
  if (path === '/trust') return { page: 'sub-trust-center' }
  if (path === '/profile/collected') return { page: 'sub-collected-preferences' }
  if (path === '/ops/workbench') return { page: 'ops-workbench' }

  const candidate = path.match(/^\/candidates\/([^/]+)$/)
  if (candidate) {
    return { page: 'sub-candidate-detail', candidateId: decodeURIComponent(candidate[1]) }
  }

  const chat = path.match(/^\/chat\/([^/]+)$/)
  if (chat) {
    return { page: 'sub-chat', chatId: decodeURIComponent(chat[1]) }
  }

  return { page: 'splash' }
}
