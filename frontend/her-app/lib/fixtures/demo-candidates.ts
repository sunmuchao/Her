/** Dev-only fixtures when NEXT_PUBLIC_ALLOW_MOCK_FALLBACK=true. Not used in production paths. */

export type DemoCandidateDetail = {
  id: string
  name: string
  age: number
  city: string
  occupation: string
  education: string
  height: string
  headline: string
  verified: boolean
  matchScore: number
  images: string[]
  selfIntro: string
  keyPoints: { label: string; value: string }[]
  needToKnow: string[]
  matchmakerNote: string
  matchReasons: string[]
}

export const DEMO_CANDIDATES_DATABASE: Record<string, DemoCandidateDetail> = {
  '1': {
    id: '1',
    name: '林悦',
    age: 28,
    city: '上海',
    occupation: '产品设计师',
    education: '复旦大学',
    height: '165cm',
    headline: '相信设计改变生活',
    verified: true,
    matchScore: 95,
    images: [
      'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=800&h=1200&fit=crop&crop=face',
      'https://images.unsplash.com/photo-1529626455594-4ff0802cfb7e?w=800&h=1200&fit=crop&crop=face',
      'https://images.unsplash.com/photo-1531746020798-e6953c6e8e04?w=800&h=1200&fit=crop&crop=face',
    ],
    selfIntro: '热爱设计，相信美好的事物能改变生活。工作之余喜欢探索城市里的小店，记录生活中的美好瞬间。',
    keyPoints: [
      { label: '作息', value: '早睡早起型' },
      { label: '饮食', value: '偏清淡' },
      { label: '运动', value: '瑜伽、游泳' },
      { label: '宠物', value: '养了一只猫' },
    ],
    needToKnow: ['她比较注重隐私，初次见面建议选择公共场所', '她有一只猫，如果你对猫过敏需要考虑'],
    matchmakerNote: '林悦是一个温和细腻的女生，对感情认真负责。建议你们可以从共同的兴趣爱好聊起。',
    matchReasons: ['你们都在上海，距离很近', '她的性格温柔，符合你的期待', '审美品味相近'],
  },
  '2': {
    id: '2',
    name: '陈思',
    age: 27,
    city: '上海',
    occupation: '品牌策划',
    education: '浙江大学',
    height: '168cm',
    headline: '在创意中寻找生活的无限可能',
    verified: true,
    matchScore: 92,
    images: [
      'https://images.unsplash.com/photo-1524504388940-b1c1722653e1?w=800&h=1200&fit=crop&crop=face',
      'https://images.unsplash.com/photo-1502823403499-6ccfcf4fb453?w=800&h=1200&fit=crop&crop=face',
    ],
    selfIntro: '热爱创意工作，喜欢用故事打动人心。周末常常泡在书店或者去看话剧。',
    keyPoints: [
      { label: '作息', value: '夜猫子型' },
      { label: '饮食', value: '美食爱好者' },
      { label: '运动', value: '跑步、网球' },
      { label: '宠物', value: '暂时没有' },
    ],
    needToKnow: ['她工作较忙，可能回复消息不及时', '她比较独立，需要个人空间'],
    matchmakerNote: '陈思是一个非常有想法的女生，事业心比较强但也渴望爱情。建议从旅行或阅读的话题聊起。',
    matchReasons: ['价值观相似，追求品质生活', '兴趣爱好有交集', '都有独立的人格'],
  },
  '3': {
    id: '3',
    name: '王晴',
    age: 26,
    city: '杭州',
    occupation: '插画师',
    education: '中国美院',
    height: '162cm',
    headline: '用画笔记录世界的美好',
    verified: true,
    matchScore: 88,
    images: [
      'https://images.unsplash.com/photo-1517841905240-472988babdf9?w=800&h=1200&fit=crop&crop=face',
      'https://images.unsplash.com/photo-1502767089025-6572583495f9?w=800&h=1200&fit=crop&crop=face',
    ],
    selfIntro: '自由插画师，用画笔讲故事。喜欢安静的生活，经常在西湖边写生。',
    keyPoints: [
      { label: '作息', value: '自由作息' },
      { label: '饮食', value: '素食为主' },
      { label: '运动', value: '散步、骑行' },
      { label: '宠物', value: '两只猫' },
    ],
    needToKnow: ['她在杭州，可能需要异地', '她是自由职业，收入不太稳定'],
    matchmakerNote: '王晴是一个非常有艺术气息的女生，性格温和，向往简单纯粹的生活。',
    matchReasons: ['艺术气质契合', '生活态度相似', '都向往简单纯粹的感情'],
  },
  '4': {
    id: '4',
    name: '张雨',
    age: 29,
    city: '北京',
    occupation: '建筑师',
    education: '清华大学',
    height: '170cm',
    headline: '在理性与浪漫之间寻找平衡',
    verified: true,
    matchScore: 85,
    images: [
      'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=800&h=1200&fit=crop&crop=face',
      'https://images.unsplash.com/photo-1488426862026-3ee34a7d66df?w=800&h=1200&fit=crop&crop=face',
    ],
    selfIntro: '建筑师，喜欢创造有温度的空间。工作之余喜欢研究咖啡和红酒。',
    keyPoints: [
      { label: '作息', value: '规律作息' },
      { label: '饮食', value: '健康饮食' },
      { label: '运动', value: '健身、普拉提' },
      { label: '宠物', value: '暂时没有' },
    ],
    needToKnow: ['她在北京，需要异地', '她对另一半要求较高'],
    matchmakerNote: '张雨是一个非常优秀的女生，事业有成但也渴望稳定的感情。',
    matchReasons: ['对未来家庭有清晰规划', '追求高品质生活', '价值观一致'],
  },
}

export const DEFAULT_DEMO_CANDIDATE = DEMO_CANDIDATES_DATABASE['1']

export const DEMO_VERIFIED_ITEMS = [
  { name: '身份信息', verified: true },
  { name: '学历认证', verified: true },
  { name: '职业信息', verified: true },
  { name: '收入水平', verified: false },
]
