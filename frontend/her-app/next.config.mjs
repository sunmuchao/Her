/** @type {import('next').NextConfig} */
const nextConfig = {
  // Next.js 16 blocks dev HMR/assets when the page host differs from the dev server host
  // (e.g. opening http://127.0.0.1:3000 while the server advertises localhost).
  allowedDevOrigins: ['127.0.0.1', 'localhost'],

  // 明确指定 Turbopack 根目录，避免多个 lockfiles 导致的推断错误
  turbopack: {
    root: process.cwd(),
  },

  images: {
    localPatterns: [
      { pathname: '/**' },
    ],
    remotePatterns: [
      { protocol: 'https', hostname: 'images.unsplash.com' },
      { protocol: 'https', hostname: 'images.pexels.com' },
      { protocol: 'https', hostname: 'randomuser.me' },
      { protocol: 'https', hostname: 'example.com' },
      // 本地资料库头像（virtual_profile_photos / partner-search seed）
      { protocol: 'https', hostname: 'cdn.her.local' },
      { protocol: 'https', hostname: 'img.her.local' },
      // MinIO 本地存储（Docker 内部 URL 转换后的外部访问地址）
      { protocol: 'http', hostname: 'localhost', port: '9000' },
      { protocol: 'http', hostname: '127.0.0.1', port: '9000' },
    ],
  },

  // 允许 unload 事件（用于 Vercel Analytics）
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'Permissions-Policy',
            value: 'unload=(self)',
          },
        ],
      },
    ]
  },
}

export default nextConfig
