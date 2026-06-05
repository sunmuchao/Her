/**
 * Assessment Theme Configurations
 *
 * Each assessment type has its own distinct visual theme to reduce visual fatigue
 * and create a unique experience for each test.
 */

export type AssessmentType =
  | 'mbti_16'
  | 'attachment_style'
  | 'big_five'
  | 'sternberg_triangular_love'
  | 'values_auction'

export interface AssessmentTheme {
  name: string
  shortName: string
  description: string
  duration: string
  questionCount: number

  // Colors
  primaryColor: string           // Main accent color class (e.g., 'text-primary')
  primaryBg: string              // Background variant (e.g., 'bg-primary/10')
  softBg: string                 // Soft background (e.g., 'bg-rose-soft')
  gradientFrom: string           // Gradient start (e.g., 'from-rose-soft')
  gradientTo: string             // Gradient end (e.g., 'to-gold-soft')

  // Progress bar colors for dimensions
  progressColors: Array<{
    key: string
    name: string
    color: string                // Tailwind bg class (e.g., 'bg-rose')
  }>

  // Icon configuration
  iconType: 'brain' | 'heart' | 'sparkles' | 'link' | 'coins'
}

export const ASSESSMENT_THEMES: Record<AssessmentType, AssessmentTheme> = {
  mbti_16: {
    name: 'MBTI 恋爱测试',
    shortName: 'MBTI',
    description: '探索你在恋爱中的性格特质',
    duration: '10-15分钟',
    questionCount: 48,

    primaryColor: 'text-primary',
    primaryBg: 'bg-primary/10',
    softBg: 'bg-rose-soft',
    gradientFrom: 'from-rose-soft',
    gradientTo: 'to-gold-soft',

    progressColors: [
      { key: 'EI', name: '社交能量', color: 'bg-rose' },
      { key: 'SN', name: '信息感知', color: 'bg-gold' },
      { key: 'TF', name: '决策方式', color: 'bg-primary' },
      { key: 'JP', name: '生活态度', color: 'bg-taupe' },
    ],

    iconType: 'brain',
  },

  attachment_style: {
    name: '依恋风格测试',
    shortName: '依恋风格',
    description: '了解你在亲密关系中的依恋模式',
    duration: '4分钟',
    questionCount: 16,

    primaryColor: 'text-coral',
    primaryBg: 'bg-coral/10',
    softBg: 'bg-coral-soft',
    gradientFrom: 'from-coral-soft',
    gradientTo: 'to-rose-soft',

    progressColors: [
      { key: 'anxiety', name: '焦虑维度', color: 'bg-coral' },
      { key: 'avoidance', name: '回避维度', color: 'bg-rose' },
      { key: 'security', name: '安全维度', color: 'bg-sage' },
      { key: 'trust', name: '信任维度', color: 'bg-gold' },
    ],

    iconType: 'link',
  },

  big_five: {
    name: '大五人格特质',
    shortName: '大五人格',
    description: '查看你的连续人格画像',
    duration: '8-10分钟',
    questionCount: 50,

    primaryColor: 'text-sage',
    primaryBg: 'bg-sage/10',
    softBg: 'bg-sage-soft',
    gradientFrom: 'from-sage-soft',
    gradientTo: 'to-gold-soft',

    progressColors: [
      { key: 'openness', name: '开放性', color: 'bg-lavender' },
      { key: 'conscientiousness', name: '尽责性', color: 'bg-sage' },
      { key: 'extraversion', name: '外向性', color: 'bg-rose' },
      { key: 'agreeableness', name: '宜人性', color: 'bg-gold' },
      { key: 'neuroticism', name: '情绪敏感度', color: 'bg-coral' },
    ],

    iconType: 'sparkles',
  },

  sternberg_triangular_love: {
    name: '爱情三元论',
    shortName: '爱情三元论',
    description: '查看亲密、激情与承诺的组合',
    duration: '3-4分钟',
    questionCount: 15,

    primaryColor: 'text-amber',
    primaryBg: 'bg-amber/10',
    softBg: 'bg-amber-soft',
    gradientFrom: 'from-amber-soft',
    gradientTo: 'to-rose-soft',

    progressColors: [
      { key: 'intimacy', name: '亲密', color: 'bg-rose' },
      { key: 'passion', name: '激情', color: 'bg-coral' },
      { key: 'commitment', name: '承诺', color: 'bg-amber' },
    ],

    iconType: 'heart',
  },

  values_auction: {
    name: '价值观拍卖会',
    shortName: '价值观',
    description: '拍卖人生选择，发现你的核心价值',
    duration: '3分钟',
    questionCount: 9,

    primaryColor: 'text-amber',
    primaryBg: 'bg-amber/10',
    softBg: 'bg-amber-soft',
    gradientFrom: 'from-amber-soft',
    gradientTo: 'to-gold-soft',

    progressColors: [
      { key: 'material', name: '物质与成就', color: 'bg-amber' },
      { key: 'emotion', name: '情感与连接', color: 'bg-rose' },
      { key: 'self', name: '自我与成长', color: 'bg-sage' },
      { key: 'altruism', name: '利他与奉献', color: 'bg-lavender' },
    ],

    iconType: 'coins',
  },
}

export function getAssessmentTheme(type: AssessmentType | undefined): AssessmentTheme {
  return ASSESSMENT_THEMES[type || 'mbti_16']
}
