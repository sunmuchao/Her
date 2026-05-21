'use client'

import { Sparkles, Heart, User } from 'lucide-react'
import type { TabType } from '@/lib/navigation/types'
import { cn } from '@/lib/utils'

interface BottomNavProps {
  currentTab: TabType
  onTabChange: (tab: TabType) => void
  matchmakerBadge?: number
  relationshipsBadge?: number
}

const tabs: { id: TabType; label: string; icon: typeof Sparkles }[] = [
  { id: 'matchmaker', label: '红娘', icon: Sparkles },
  { id: 'relationships', label: '关系', icon: Heart },
  { id: 'profile', label: '我的', icon: User },
]

export default function BottomNav({ 
  currentTab, 
  onTabChange, 
  matchmakerBadge = 0,
  relationshipsBadge = 0 
}: BottomNavProps) {
  return (
    <nav 
      className="fixed bottom-0 left-0 right-0 max-w-md mx-auto z-50 bg-background border-t border-border safe-area-bottom"
      role="tablist"
      aria-label="主导航"
    >
      <div className="flex items-center justify-around h-14">
        {tabs.map((tab) => {
          const isActive = currentTab === tab.id
          const Icon = tab.icon
          const badge = tab.id === 'matchmaker' ? matchmakerBadge : 
                       tab.id === 'relationships' ? relationshipsBadge : 0
          
          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              role="tab"
              aria-selected={isActive}
              aria-label={`${tab.label}${badge > 0 ? `，${badge}条新消息` : ''}`}
              className={cn(
                'relative flex flex-col items-center justify-center w-16 h-full transition-all',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background rounded-lg',
                isActive && 'scale-105'
              )}
            >
              <div className="relative">
                <Icon 
                  className={cn(
                    'w-5 h-5 transition-all duration-200',
                    isActive ? 'text-primary scale-110' : 'text-muted-foreground'
                  )} 
                  aria-hidden="true"
                />
                {badge > 0 && (
                  <span 
                    className="absolute -top-1 -right-2 min-w-[16px] h-4 px-1 bg-rose text-[10px] font-medium text-white rounded-full flex items-center justify-center animate-scale-in"
                    aria-hidden="true"
                  >
                    {badge > 99 ? '99+' : badge}
                  </span>
                )}
              </div>
              <span 
                className={cn(
                  'text-[10px] mt-1 transition-all duration-200',
                  isActive ? 'text-primary font-medium' : 'text-muted-foreground'
                )}
              >
                {tab.label}
              </span>
              {/* Active indicator */}
              {isActive && (
                <span className="absolute -bottom-0 left-1/2 -translate-x-1/2 w-4 h-0.5 bg-primary rounded-full animate-scale-in" />
              )}
            </button>
          )
        })}
      </div>
    </nav>
  )
}
