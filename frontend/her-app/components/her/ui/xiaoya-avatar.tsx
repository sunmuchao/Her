import Image from 'next/image'
import { cn } from '@/lib/utils'

const AVATAR_SRC = '/xiaoya-avatar.png?v=5'

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

// Typing indicator version of avatar
export function XiaoyaAvatarTyping({
  size = 40,
  className = '',
}: Omit<XiaoyaAvatarProps, 'showOnlineStatus' | 'isOnline'>) {
  return (
    <div className={cn('relative', className)}>
      <XiaoyaAvatar size={size} showOnlineStatus={false} />
      <span className="absolute -bottom-1 -right-1 flex items-center justify-center">
        <span className="flex gap-0.5">
          <span
            className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-primary"
            style={{ animationDelay: '0ms' }}
          />
          <span
            className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-primary"
            style={{ animationDelay: '150ms' }}
          />
          <span
            className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-primary"
            style={{ animationDelay: '300ms' }}
          />
        </span>
      </span>
    </div>
  )
}
