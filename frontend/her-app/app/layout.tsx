import type { Metadata, Viewport } from 'next'
import { Inter, Cormorant_Garamond } from 'next/font/google'
import { Analytics } from '@vercel/analytics/next'
import { AppConnectivityProvider, OfflineBanner } from '@/components/her/ui/app-connectivity'
import { ThemeProvider } from '@/components/theme-provider'
import { Toaster } from '@/components/ui/sonner'
import './globals.css'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
})

const cormorant = Cormorant_Garamond({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-cormorant',
  display: 'swap',
})

export const metadata: Metadata = {
  title: '小雅 - 你的专属红娘',
  description: '认真关系，从认真了解开始',
  icons: {
    icon: [
      {
        url: '/icon-light-32x32.png',
        media: '(prefers-color-scheme: light)',
      },
      {
        url: '/icon-dark-32x32.png',
        media: '(prefers-color-scheme: dark)',
      },
      {
        url: '/xiaoya-avatar.png',
        type: 'image/png',
      },
    ],
    apple: '/apple-icon.png',
  },
}

export const viewport: Viewport = {
  themeColor: '#F5F0EB',
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning className={`${inter.variable} ${cormorant.variable}`}>
      <body className="font-sans antialiased bg-background">
        <a
          href="#main-content"
          className="skip-link sr-only focus:not-sr-only"
        >
          跳转到主要内容
        </a>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          <AppConnectivityProvider>
            <OfflineBanner />
            <main id="main-content">{children}</main>
            <Toaster richColors position="top-center" />
            {process.env.NODE_ENV === 'production' && <Analytics />}
          </AppConnectivityProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
