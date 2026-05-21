import Image from 'next/image'

const AVATAR_SRC = '/xiaoya-avatar.png'

type XiaoyaAvatarProps = {
  size?: number
  className?: string
  priority?: boolean
}

export function XiaoyaAvatar({ size = 40, className = '', priority = false }: XiaoyaAvatarProps) {
  return (
    <div
      className={`relative shrink-0 overflow-hidden rounded-full ${className}`}
      style={{ width: size, height: size }}
    >
      <Image
        src={AVATAR_SRC}
        alt="小雅"
        width={size}
        height={size}
        className="h-full w-full object-cover"
        priority={priority}
      />
    </div>
  )
}
