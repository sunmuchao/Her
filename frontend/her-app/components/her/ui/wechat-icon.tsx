import Image from 'next/image'

const WECHAT_ICON_SRC = '/wechat-icon.png'

type WechatIconProps = {
  size?: number
  className?: string
}

export function WechatIcon({ size = 20, className = '' }: WechatIconProps) {
  return (
    <span
      className={`relative inline-flex shrink-0 overflow-hidden rounded-full ${className}`}
      style={{ width: size, height: size }}
    >
      <Image
        src={WECHAT_ICON_SRC}
        alt="微信"
        width={size}
        height={size}
        className="h-full w-full object-cover"
      />
    </span>
  )
}
