import { NextRequest, NextResponse } from 'next/server'
import type { FeedbackCategory, FeedbackRecord } from '@/lib/feedback/types'
import { appendFeedbackRecord, readFeedbackRecords } from '@/lib/server/feedback-store'

const ALLOWED_CATEGORIES = new Set<FeedbackCategory>(['bug', 'ux', 'account', 'suggestion'])

function badRequest(message: string) {
  return NextResponse.json({ error: message }, { status: 400 })
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

  const category = typeof body.category === 'string' ? body.category.trim() as FeedbackCategory : ''
  const content = typeof body.content === 'string' ? body.content.trim() : ''
  const contact = typeof body.contact === 'string' ? body.contact.trim() : ''

  if (!ALLOWED_CATEGORIES.has(category)) {
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
    category,
    content,
    contact,
    createdAt: new Date().toISOString(),
  }

  try {
    const records = await appendFeedbackRecord(record)
    return NextResponse.json({ record, records })
  } catch {
    return NextResponse.json({ error: 'feedback_write_failed' }, { status: 500 })
  }
}
