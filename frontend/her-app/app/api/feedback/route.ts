import { NextRequest, NextResponse } from 'next/server'
import type { FeedbackCategory, FeedbackRecord } from '@/lib/feedback/types'
import { appendFeedbackRecord, readFeedbackRecords } from '@/lib/server/feedback-store'

const ALLOWED_CATEGORIES = new Set<FeedbackCategory>(['bug', 'ux', 'account', 'suggestion'])
const SESSION_CONTEXT_COOKIE = 'her_session_ctx'

function badRequest(message: string) {
  return NextResponse.json({ error: message }, { status: 400 })
}

function isFeedbackCategory(value: string): value is FeedbackCategory {
  return ALLOWED_CATEGORIES.has(value as FeedbackCategory)
}

function resolveSubmitter(request: NextRequest) {
  const raw = request.cookies.get(SESSION_CONTEXT_COOKIE)?.value
  if (!raw) {
    return {
      userId: 'anonymous',
    }
  }

  try {
    const parsed = JSON.parse(raw) as {
      userId?: unknown
      profileId?: unknown
    }
    return {
      userId: typeof parsed.userId === 'string' && parsed.userId.trim() ? parsed.userId.trim() : 'anonymous',
      profileId: typeof parsed.profileId === 'number' ? parsed.profileId : undefined,
      authSource: request.headers.get('x-her-auth-source') || undefined,
    }
  } catch {
    return {
      userId: 'anonymous',
    }
  }
}

export async function GET() {
  try {
    const records = await readFeedbackRecords()
    return NextResponse.json({ records })
  } catch {
    return NextResponse.json({ error: 'feedback_read_failed' }, { status: 500 })
  }
}

export async function POST(request: NextRequest) {
  let body: Partial<FeedbackRecord>
  try {
    body = (await request.json()) as Partial<FeedbackRecord>
  } catch {
    return badRequest('invalid_json')
  }

  const rawCategory = typeof body.category === 'string' ? body.category.trim() : ''
  const content = typeof body.content === 'string' ? body.content.trim() : ''
  const contact = typeof body.contact === 'string' ? body.contact.trim() : ''

  if (!isFeedbackCategory(rawCategory)) {
    return badRequest('invalid_category')
  }
  if (content.length < 10 || content.length > 500) {
    return badRequest('invalid_content_length')
  }
  if (contact.length > 60) {
    return badRequest('invalid_contact_length')
  }

  const record: FeedbackRecord = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    category: rawCategory,
    content,
    contact,
    createdAt: new Date().toISOString(),
    status: 'submitted',
    submitter: resolveSubmitter(request),
  }

  try {
    const records = await appendFeedbackRecord(record)
    return NextResponse.json({ record, records })
  } catch {
    return NextResponse.json({ error: 'feedback_write_failed' }, { status: 500 })
  }
}
