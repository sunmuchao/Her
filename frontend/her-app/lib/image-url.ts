const DEV_PLACEHOLDER_AVATAR =
  'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=800&h=1200&fit=crop&crop=face'

const LOCAL_CDN_HOSTS = new Set(['cdn.her.local', 'img.her.local'])

export function isLocalDevCdnUrl(url: string): boolean {
  try {
    return LOCAL_CDN_HOSTS.has(new URL(url).hostname)
  } catch {
    return false
  }
}

/** Local seed URLs often have no DNS; use placeholder in dev so pages still render. */
export function resolveProfileImageUrl(url: string | undefined, fallback = DEV_PLACEHOLDER_AVATAR): string {
  if (!url?.trim()) return fallback
  if (process.env.NODE_ENV === 'development' && isLocalDevCdnUrl(url)) {
    return fallback
  }
  return url
}

export function mapProfileImageUrls(urls: string[], fallback = DEV_PLACEHOLDER_AVATAR): string[] {
  const mapped = urls.map((u) => resolveProfileImageUrl(u, fallback))
  return mapped.length ? mapped : [fallback]
}
