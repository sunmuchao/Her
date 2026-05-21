import { NextRequest, NextResponse } from 'next/server'

const ACCESS_COOKIE = 'her_access_token'
const CONTEXT_COOKIE = 'her_session_ctx'
const MAX_AGE = 60 * 60 * 24 * 7

function cookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    path: '/',
    maxAge: MAX_AGE,
  }
}

export async function POST(request: NextRequest) {
  let body: { access_token?: string; context?: Record<string, unknown> } = {}
  try {
    body = (await request.json()) as typeof body
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 })
  }

  const token = (body.access_token || '').trim()
  if (!token) {
    return NextResponse.json({ error: 'access_token_required' }, { status: 400 })
  }

  const response = NextResponse.json({ ok: true })
  response.cookies.set(ACCESS_COOKIE, token, cookieOptions())
  if (body.context) {
    response.cookies.set(CONTEXT_COOKIE, JSON.stringify(body.context), cookieOptions())
  }
  return response
}

export async function DELETE() {
  const response = NextResponse.json({ ok: true })
  response.cookies.set(ACCESS_COOKIE, '', { ...cookieOptions(), maxAge: 0 })
  response.cookies.set(CONTEXT_COOKIE, '', { ...cookieOptions(), maxAge: 0 })
  return response
}
