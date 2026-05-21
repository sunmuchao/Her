import Image from 'next/image'

const AVATAR_SRC = '/xiaoya-avatar.png?v=5'

type XiaoyaAvatarProps = {
  size?: number
  className?: string
  priority?: boolean
}

export function XiaoyaAvatar({ size = 40, className = '', priority = false }: XiaoyaAvatarProps) {
  return (
    <Image
      src={AVATAR_SRC}
      alt="小雅"
      width={size}
      height={size}
      className={`block shrink-0 rounded-full object-cover ${className}`}
      style={{ width: size, height: size, background: 'transparent' }}
      priority={priority}
    />
  )
}
