import { DEMO_DEFAULT_CANDIDATE_ID, DEMO_DEFAULT_CHAT_ID } from '@/lib/navigation/defaults'
import type { AppPage } from '@/lib/navigation/types'

export type RouteParams = {
  candidateId?: string
  chatId?: string
  caseId?: string
  viewType?: 'delayed' | 'matched' | 'interest' | 'candidate'
  chatTitle?: string
  counterpartId?: string
  fromChatId?: string
  fromSubPage?: string
  inboxFilter?: string
}

export type ParsedRoute = RouteParams & {
  page: AppPage
}

export function pageToPath(page: AppPage, params: RouteParams = {}): string {
  let path: string
  switch (page) {
    case 'splash':
      path = '/splash'
      break
    case 'auth-welcome':
      path = '/welcome'
      break
    case 'auth-one-click':
      path = '/login/one-tap'
      break
    case 'auth-phone':
      path = '/login/phone'
      break
    case 'auth-verification-code':
      path = '/login/verify'
      break
    case 'auth-wechat-binding':
      path = '/wechat/bind'
      break
    case 'auth-new-user-welcome':
      path = '/onboarding/welcome'
      break
    case 'auth-onboarding':
      path = '/onboarding'
      break
    case 'auth-recovery':
      path = '/recovery'
      break
    case 'main-matchmaker':
      path = '/discover'
      break
    case 'main-relationships':
      path = '/relationships'
      break
    case 'main-profile':
      path = '/profile'
      break
    case 'sub-candidate-detail':
      path = `/candidates/${params.candidateId ?? DEMO_DEFAULT_CANDIDATE_ID}`
      break
    case 'sub-chat':
      path = `/chat/${params.chatId ?? DEMO_DEFAULT_CHAT_ID}`
      break
    case 'sub-verification':
      path = '/verification'
      break
    case 'sub-collected-preferences':
      path = '/profile/collected'
      break
    case 'sub-edit-profile':
      path = '/profile/edit'
      break
    case 'sub-settings':
      path = '/settings'
      break
    case 'ops-workbench':
      path = '/ops/workbench'
      break
    default:
      path = '/splash'
      break
  }

  // 添加 query 参数：caseId, viewType, chatTitle, counterpartId, fromChatId, fromSubPage, inboxFilter
  const queryParams: string[] = []
  if (params.caseId) {
    queryParams.push(`caseId=${encodeURIComponent(params.caseId)}`)
  }
  if (params.viewType) {
    queryParams.push(`viewType=${encodeURIComponent(params.viewType)}`)
  }
  if (params.chatTitle) {
    queryParams.push(`chatTitle=${encodeURIComponent(params.chatTitle)}`)
  }
  if (params.counterpartId) {
    queryParams.push(`counterpartId=${encodeURIComponent(params.counterpartId)}`)
  }
  if (params.fromChatId) {
    queryParams.push(`fromChatId=${encodeURIComponent(params.fromChatId)}`)
  }
  if (params.fromSubPage) {
    queryParams.push(`fromSubPage=${encodeURIComponent(params.fromSubPage)}`)
  }
  if (params.inboxFilter) {
    queryParams.push(`inboxFilter=${encodeURIComponent(params.inboxFilter)}`)
  }
  if (queryParams.length > 0) {
    path += '?' + queryParams.join('&')
  }

  return path
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
  if (path === '/verification') return { page: 'sub-verification' }
  if (path === '/trust') return { page: 'main-profile' }
  if (path === '/profile/collected') return { page: 'sub-collected-preferences' }
  if (path === '/profile/edit') return { page: 'sub-edit-profile' }
  if (path === '/settings') return { page: 'sub-settings' }
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
