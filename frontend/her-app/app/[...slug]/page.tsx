'use client'

import { Suspense } from 'react'
import { HerApp } from '@/components/app/her-app'

export default function HerSlugPage() {
  return (
    <Suspense fallback={null}>
      <HerApp />
    </Suspense>
  )
}
