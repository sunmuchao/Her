import type { CandidatePreview } from '@/lib/types/candidate'

/** Dev-only fixtures when NEXT_PUBLIC_ALLOW_MOCK_FALLBACK=true. Not used in production paths. */
export const DEMO_PROFILE = {
  name: '苏晴',
  age: 26,
  city: '上海',
  avatar: 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=200&h=200&fit=crop&crop=face',
  headline: '相信美好，期待遇见',
  verified: true,
  occupation: '市场经理',
  education: '上海交通大学 · 硕士',
  relationshipGoal: '认真恋爱，期待结婚',
  tags: ['温柔', '独立', '爱阅读'],
}

export const DEMO_CANDIDATES: CandidatePreview[] = [
  {
    id: 'demo-1',
    name: '林悦',
    age: 28,
    city: '上海',
    occupation: '产品设计师',
    education: '复旦大学',
    verified: true,
    matchScore: 95,
    image: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400&h=600&fit=crop&crop=face',
    matchReason: '性格温和、同城、审美品味相近',
  },
  {
    id: 'demo-2',
    name: '陈思',
    age: 27,
    city: '上海',
    occupation: '品牌策划',
    education: '浙江大学',
    verified: true,
    matchScore: 92,
    image: 'https://images.unsplash.com/photo-1524504388940-b1c1722653e1?w=400&h=600&fit=crop&crop=face',
    matchReason: '价值观相似、兴趣爱好匹配',
  },
]

export const DEMO_CHAT_MESSAGES = [
  { id: 'demo-1', type: 'received' as const, content: '你好呀，很高兴认识你～', timestamp: '10:30' },
  { id: 'demo-2', type: 'sent' as const, content: '你好！很高兴认识你。', timestamp: '10:32', status: 'read' as const },
]

export const EMPTY_PREFS_PLACEHOLDER = '暂未收集到偏好'
