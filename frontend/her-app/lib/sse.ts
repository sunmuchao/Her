export const DEFAULT_SSE_SERVER_URL = 'http://localhost:8081'

export function getSSEServerUrl(): string {
  return process.env.NEXT_PUBLIC_SSE_SERVER_URL || DEFAULT_SSE_SERVER_URL
}
