'use client'

import { Menu, X } from 'lucide-react'
import { useState } from 'react'
import { demoPageCategories } from '@/lib/navigation/demo-pages'
import type { AppPage } from '@/lib/navigation/types'

type DemoNavProps = {
  currentPage: AppPage
  onNavigate: (page: AppPage) => void
}

export function DemoNav({ currentPage, onNavigate }: DemoNavProps) {
  const [showNav, setShowNav] = useState(false)

  return (
    <>
      <button
        type="button"
        onClick={() => setShowNav(!showNav)}
        aria-label={showNav ? '关闭页面导航' : '打开页面导航'}
        className="fixed bottom-6 right-6 z-[100] w-14 h-14 rounded-full bg-primary text-primary-foreground shadow-elevated flex items-center justify-center transition-transform hover:scale-105 active:scale-95"
      >
        {showNav ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
      </button>

      {showNav && (
        <>
          <div
            className="fixed inset-0 bg-black/40 z-[90] backdrop-blur-sm"
            onClick={() => setShowNav(false)}
            aria-hidden="true"
          />
          <div className="fixed bottom-24 right-6 z-[100] w-72 max-h-[70vh] overflow-y-auto bg-card rounded-2xl shadow-elevated border border-border/50">
            <div className="p-4 border-b border-border/50">
              <h3 className="font-serif text-lg text-foreground">页面导航</h3>
              <p className="text-xs text-muted-foreground mt-1">仅开发 / 联调使用</p>
            </div>
            <div className="p-2">
              {demoPageCategories.map((category) => (
                <div key={category.name} className="mb-4">
                  <h4 className="text-xs font-medium text-muted-foreground px-2 py-1 uppercase tracking-wider">
                    {category.name}
                  </h4>
                  <div className="space-y-1">
                    {category.pages.map((page) => {
                      const Icon = page.icon
                      const isActive = currentPage === page.id
                      return (
                        <button
                          key={page.id}
                          type="button"
                          onClick={() => {
                            onNavigate(page.id)
                            setShowNav(false)
                          }}
                          className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-colors ${
                            isActive
                              ? 'bg-primary/10 text-primary'
                              : 'hover:bg-muted/50 text-foreground'
                          }`}
                        >
                          <Icon className="w-4 h-4 flex-shrink-0" />
                          <span className="text-sm">{page.name}</span>
                          {isActive && (
                            <span className="ml-auto w-2 h-2 rounded-full bg-primary" />
                          )}
                        </button>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  )
}
