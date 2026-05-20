'use client'

import { Compass, Inbox, Heart, Shield, User } from 'lucide-react'
import type { TabType } from '@/app/page'

interface BottomNavProps {
  currentTab: TabType
  onTabChange: (tab: TabType) => void
}

const tabs: { id: TabType; label: string; icon: typeof Compass }[] = [
  { id: 'discover', label: '发现', icon: Compass },
  { id: 'recommendations', label: '推荐', icon: Inbox },
  { id: 'relationships', label: '关系', icon: Heart },
  { id: 'trust', label: '信任', icon: Shield },
  { id: 'profile', label: '我的', icon: User },
]

export default function BottomNav({ currentTab, onTabChange }: BottomNavProps) {
  return (
    <nav className="fixed bottom-0 left-0 right-0 max-w-md mx-auto z-50 safe-area-bottom">
      {/* Frosted glass background */}
      <div className="absolute inset-0 glass-soft border-t border-border/50" />
      
      <div className="relative flex items-center justify-around px-2 py-3">
        {tabs.map((tab) => {
          const isActive = currentTab === tab.id
          const Icon = tab.icon
          
          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={`flex flex-col items-center gap-1 px-4 py-2 rounded-2xl transition-all duration-300 ${
                isActive 
                  ? 'bg-rose-soft/60' 
                  : 'hover:bg-secondary/50'
              }`}
            >
              <Icon 
                className={`w-5 h-5 transition-colors duration-300 ${
                  isActive ? 'text-primary' : 'text-muted-foreground'
                }`}
                strokeWidth={isActive ? 2 : 1.5}
              />
              <span 
                className={`text-[10px] font-medium transition-colors duration-300 ${
                  isActive ? 'text-primary' : 'text-muted-foreground'
                }`}
              >
                {tab.label}
              </span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}
