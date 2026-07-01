import { mkdir, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import type { FeedbackRecord } from '@/lib/feedback/types'

const DATA_DIR = path.join(process.cwd(), '.data')
const DATA_FILE = path.join(DATA_DIR, 'feedback-records.json')

async function ensureDataDir() {
  await mkdir(DATA_DIR, { recursive: true })
}

export async function readFeedbackRecords(): Promise<FeedbackRecord[]> {
  try {
    const raw = await readFile(DATA_FILE, 'utf8')
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item): item is FeedbackRecord => {
      return (
        typeof item === 'object' &&
        item !== null &&
        typeof item.id === 'string' &&
        typeof item.category === 'string' &&
        typeof item.content === 'string' &&
        typeof item.contact === 'string' &&
        typeof item.createdAt === 'string'
      )
    })
  } catch (error) {
    const code = typeof error === 'object' && error !== null && 'code' in error ? error.code : ''
    if (code === 'ENOENT') return []
    throw error
  }
}

export async function appendFeedbackRecord(record: FeedbackRecord): Promise<FeedbackRecord[]> {
  const records = await readFeedbackRecords()
  const nextRecords = [record, ...records].slice(0, 100)
  await ensureDataDir()
  await writeFile(DATA_FILE, JSON.stringify(nextRecords, null, 2), 'utf8')
  return nextRecords
}
