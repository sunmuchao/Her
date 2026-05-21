/** @type {import('next').NextConfig} */
const nextConfig = {
  // Next.js 16 blocks dev HMR/assets when the page host differs from the dev server host
  // (e.g. opening http://127.0.0.1:3000 while the server advertises localhost).
  allowedDevOrigins: ['127.0.0.1', 'localhost'],
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
}

export default nextConfig
