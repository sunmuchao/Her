const PLACEHOLDER_AVATAR_SVG = encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200"><rect fill="#e5e7eb" width="200" height="200"/><circle cx="100" cy="78" r="36" fill="#9ca3af"/><ellipse cx="100" cy="168" rx="52" ry="44" fill="#9ca3af"/></svg>',
)

export const PLACEHOLDER_AVATAR = `data:image/svg+xml,${PLACEHOLDER_AVATAR_SVG}`

const DEV_PLACEHOLDER_AVATAR = PLACEHOLDER_AVATAR

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
