import { wechatLogin } from '@/lib/auth/auth-api'
import { applyLoginPayload, getAccessToken } from '@/lib/auth/session'
import { isAuthStubEnabled } from '@/lib/env'

/** Dev-only: obtain access token via WeChat stub when stub mode is on and user skipped login. */
export async function ensureDevAuthSession(): Promise<boolean> {
  if (!isAuthStubEnabled() || getAccessToken()) {
    return Boolean(getAccessToken())
  }
  try {
    const payload = await wechatLogin()
    applyLoginPayload(payload)
    return Boolean(getAccessToken())
  } catch {
    return false
  }
}
