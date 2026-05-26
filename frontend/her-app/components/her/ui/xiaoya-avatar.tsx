import Image from 'next/image'
import { cn } from '@/lib/utils'

const AVATAR_SRC = '/xiaoya-avatar.png'

type XiaoyaAvatarProps = {
  size?: number
  className?: string
  priority?: boolean
  showOnlineStatus?: boolean
  isOnline?: boolean
}

export function XiaoyaAvatar({
  size = 40,
  className = '',
  priority = false,
  showOnlineStatus = false,
  isOnline = true,
}: XiaoyaAvatarProps) {
  return (
    <div
      className={cn('relative shrink-0', className)}
      style={{ width: size, height: size }}
    >
      <div className="relative h-full w-full overflow-hidden rounded-full ring-2 ring-primary/10">
        <Image
          src={AVATAR_SRC}
          alt="小雅 - 你的专属红娘"
          width={size}
          height={size}
          className="h-full w-full object-cover"
          style={{ background: 'transparent' }}
          priority={priority}
        />
      </div>
      {showOnlineStatus && (
        <span
          className={cn(
            'absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-background',
            isOnline ? 'bg-emerald-500' : 'bg-muted-foreground',
          )}
          aria-label={isOnline ? '在线' : '离线'}
        />
      )}
    </div>
  )
}
