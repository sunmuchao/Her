/** Format ISO / RFC timestamps for chat-style relative display (zh-CN). */
export function formatRelativeTime(timestamp: string | undefined | null): string {
  if (!timestamp || timestamp === '刚刚') return '刚刚'

  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return '刚刚'

  const now = new Date()
  const diff = now.getTime() - date.getTime()

  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}小时前`

  const sameYear = date.getFullYear() === now.getFullYear()
  if (sameYear) {
    return date.toLocaleString('zh-CN', {
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
