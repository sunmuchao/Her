/**
 * Assessment Theme Configurations
 * 
 * Each assessment type has its own distinct visual theme to reduce visual fatigue
 * and create a unique experience for each test.
 */

export type AssessmentType = 'mbti_16' | 'attachment_style' | 'love_language'

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
  iconType: 'brain' | 'heart' | 'sparkles' | 'link' | 'message-heart'
}

export const ASSESSMENT_THEMES: Record<AssessmentType, AssessmentTheme> = {
  mbti_16: {
    name: 'MBTI 恋爱测试',
    shortName: 'MBTI',
    description: '探索你在恋爱中的性格特质',
    duration: '5分钟',
    questionCount: 20,
    
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
  
  love_language: {
    name: '恋爱语言测试',
    shortName: '恋爱语言',
    description: '发现你表达和接收爱的方式',
    duration: '3分钟',
    questionCount: 15,
    
    primaryColor: 'text-lavender',
    primaryBg: 'bg-lavender/10',
    softBg: 'bg-lavender-soft',
    gradientFrom: 'from-lavender-soft',
    gradientTo: 'to-sage-soft',
    
    progressColors: [
      { key: 'words', name: '肯定言词', color: 'bg-lavender' },
      { key: 'time', name: '精心时刻', color: 'bg-sage' },
      { key: 'gifts', name: '接受礼物', color: 'bg-gold' },
      { key: 'service', name: '服务行动', color: 'bg-coral' },
      { key: 'touch', name: '身体接触', color: 'bg-rose' },
    ],
    
    iconType: 'message-heart',
  },
}

export function getAssessmentTheme(type: AssessmentType | undefined): AssessmentTheme {
  return ASSESSMENT_THEMES[type || 'mbti_16']
}
