'use client'

import { Heart, MessageCircle, Search } from 'lucide-react'

export function EmptyRecommendations({ onRefresh }: { onRefresh?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-8">
      <div className="w-16 h-16 bg-secondary rounded-full flex items-center justify-center mb-4">
        <Heart className="w-7 h-7 text-muted-foreground" />
      </div>
      <h3 className="font-medium text-foreground mb-1">暂时没有新的推荐</h3>
      <p className="text-sm text-muted-foreground text-center mb-4">
        小雅正在为你寻找合适的人选
      </p>
      {onRefresh && (
        <button onClick={onRefresh} className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium">
          告诉小雅你的期待
        </button>
      )}
    </div>
  )
}

export function EmptyConversations() {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-8">
      <div className="w-16 h-16 bg-secondary rounded-full flex items-center justify-center mb-4">
        <MessageCircle className="w-7 h-7 text-muted-foreground" />
      </div>
      <h3 className="font-medium text-foreground mb-1">还没有进行中的对话</h3>
      <p className="text-sm text-muted-foreground text-center">
        去和小雅聊聊，她会帮你找到合适的人
      </p>
    </div>
  )
}

export function EmptySearchResults({ keyword }: { keyword: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-8">
      <div className="w-14 h-14 bg-secondary rounded-full flex items-center justify-center mb-4">
        <Search className="w-6 h-6 text-muted-foreground" />
      </div>
      <h3 className="font-medium text-foreground mb-1">没有找到相关结果</h3>
      <p className="text-sm text-muted-foreground text-center">
        尝试其他关键词搜索「{keyword}」
      </p>
    </div>
  )
}
