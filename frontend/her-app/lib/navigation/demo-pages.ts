import {
  ClipboardList,
  Heart,
  KeyRound,
  LayoutDashboard,
  Link2,
  LogIn,
  MessageCircle,
  Phone,
  RotateCcw,
  Sparkles,
  User,
  UserPlus,
} from 'lucide-react'
import type { AppPage } from '@/lib/navigation/types'

export const demoPageCategories: Array<{
  name: string
  pages: Array<{ id: AppPage; name: string; icon: typeof Sparkles }>
}> = [
  {
    name: '启动 & 账户',
    pages: [
      { id: 'splash', name: '启动页', icon: Sparkles },
      { id: 'auth-welcome', name: '欢迎页', icon: LogIn },
      { id: 'auth-phone', name: '手机号登录', icon: Phone },
      { id: 'auth-verification-code', name: '验证码', icon: KeyRound },
      { id: 'auth-wechat-binding', name: '微信绑定', icon: Link2 },
      { id: 'auth-new-user-welcome', name: '新用户欢迎', icon: UserPlus },
      { id: 'auth-onboarding', name: '资料填写', icon: ClipboardList },
      { id: 'auth-recovery', name: '账号找回', icon: RotateCcw },
    ],
  },
  {
    name: '主功能 (3 Tab)',
    pages: [
      { id: 'main-matchmaker', name: '红娘', icon: Sparkles },
      { id: 'main-relationships', name: '关系', icon: Heart },
      { id: 'main-profile', name: '我的', icon: User },
    ],
  },
  {
    name: '二级页面',
    pages: [
      { id: 'sub-candidate-detail', name: '候选人详情', icon: User },
      { id: 'sub-chat', name: '聊天', icon: MessageCircle },
      { id: 'ops-workbench', name: '运营协作台', icon: LayoutDashboard },
    ],
  },
]
