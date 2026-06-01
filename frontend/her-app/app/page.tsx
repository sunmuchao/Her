'use client'

import { Suspense } from 'react'
import { HerApp } from '@/components/app/her-app'

export default function HomePage() {
  return (
    <Suspense fallback={null}>
      <HerApp />
    </Suspense>
  )
}