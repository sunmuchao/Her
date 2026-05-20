'use client'

import { Shield, BadgeCheck, AlertTriangle, FileText, Clock, ChevronRight, CheckCircle, XCircle, Upload } from 'lucide-react'

interface TrustCenterPageProps {
  onStartVerification: () => void
}

const verificationStatus = {
  overall: '已认证',
  overallLevel: 'verified',
  items: [
    { name: '身份认证', status: 'verified', description: '已通过实名认证' },
    { name: '学历认证', status: 'verified', description: '复旦大学 · 本科' },
    { name: '职业认证', status: 'pending', description: '审核中，预计1-2个工作日' },
    { name: '收入认证', status: 'unverified', description: '可选认证，提升可信度' },
  ],
}

const pendingItems = [
  {
    id: '1',
    title: '职业认证材料',
    description: '请补充在职证明或工牌照片',
    dueDate: '2024年3月15日前',
    urgent: false,
  },
]

const riskRecords = [
  {
    id: '1',
    type: 'warning',
    title: '账号安全提醒',
    description: '检测到异地登录，请确认是否本人操作',
    time: '3天前',
    resolved: true,
  },
]

const notifications = [
  {
    id: '1',
    title: '学历认证已通过',
    description: '你的学历信息已成功认证',
    time: '1天前',
    read: true,
  },
  {
    id: '2',
    title: '职业认证提交成功',
    description: '材料已提交，请耐心等待审核',
    time: '2天前',
    read: true,
  },
]

export default function TrustCenterPage({ onStartVerification }: TrustCenterPageProps) {
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'verified':
        return <CheckCircle className="w-5 h-5 text-green-600" />
      case 'pending':
        return <Clock className="w-5 h-5 text-gold" />
      case 'unverified':
        return <XCircle className="w-5 h-5 text-muted-foreground" />
      default:
        return null
    }
  }

  const getStatusText = (status: string) => {
    switch (status) {
      case 'verified':
        return '已认证'
      case 'pending':
        return '审核中'
      case 'unverified':
        return '未认证'
      default:
        return ''
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="sticky top-0 z-20 safe-area-top">
        <div className="glass-soft border-b border-border/30">
          <div className="px-5 py-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary to-rose flex items-center justify-center">
                <Shield className="w-5 h-5 text-primary-foreground" />
              </div>
              <div>
                <h1 className="editorial-title text-2xl text-foreground">信任中心</h1>
                <p className="text-xs text-muted-foreground">安全、透明、值得信赖</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">
        {/* Overall status card */}
        <section className="bg-gradient-to-br from-card via-card to-blush/30 rounded-3xl p-5 shadow-soft border border-rose-soft/30">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-14 h-14 rounded-full bg-green-100 flex items-center justify-center">
              <BadgeCheck className="w-7 h-7 text-green-600" />
            </div>
            <div>
              <h2 className="text-lg font-medium text-foreground">可信度良好</h2>
              <p className="text-sm text-muted-foreground">3项已认证 · 1项审核中</p>
            </div>
          </div>

          <div className="grid grid-cols-4 gap-2">
            {verificationStatus.items.map((item, index) => (
              <div
                key={index}
                className={`text-center p-2 rounded-xl ${
                  item.status === 'verified' ? 'bg-green-50' :
                  item.status === 'pending' ? 'bg-gold-soft/50' : 'bg-secondary/50'
                }`}
              >
                <div className="flex justify-center mb-1">
                  {getStatusIcon(item.status)}
                </div>
                <span className="text-[10px] text-muted-foreground">{item.name.slice(0, 2)}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Verification items */}
        <section>
          <h2 className="text-sm font-medium text-foreground mb-3">认证状态</h2>
          <div className="bg-card rounded-2xl shadow-soft border border-border/50 overflow-hidden">
            {verificationStatus.items.map((item, index) => (
              <button
                key={index}
                onClick={item.status === 'unverified' ? onStartVerification : undefined}
                className={`w-full px-4 py-4 flex items-center gap-3 text-left transition-colors hover:bg-secondary/30 ${
                  index !== verificationStatus.items.length - 1 ? 'border-b border-border/30' : ''
                }`}
              >
                {getStatusIcon(item.status)}
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-medium text-foreground">{item.name}</h3>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                      item.status === 'verified' ? 'bg-green-100 text-green-700' :
                      item.status === 'pending' ? 'bg-gold-soft text-gold' : 'bg-secondary text-muted-foreground'
                    }`}>
                      {getStatusText(item.status)}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">{item.description}</p>
                </div>
                {item.status === 'unverified' && (
                  <ChevronRight className="w-5 h-5 text-muted-foreground" />
                )}
              </button>
            ))}
          </div>
        </section>

        {/* Pending items */}
        {pendingItems.length > 0 && (
          <section>
            <h2 className="text-sm font-medium text-foreground mb-3">待处理事项</h2>
            <div className="space-y-3">
              {pendingItems.map((item) => (
                <button
                  key={item.id}
                  onClick={onStartVerification}
                  className="w-full bg-gradient-to-r from-gold-soft/50 to-card rounded-2xl p-4 shadow-soft border border-gold/20 transition-all hover:shadow-elevated active:scale-[0.99] text-left"
                >
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 rounded-full bg-gold/20 flex items-center justify-center">
                      <Upload className="w-5 h-5 text-gold" />
                    </div>
                    <div className="flex-1">
                      <h3 className="text-sm font-medium text-foreground">{item.title}</h3>
                      <p className="text-xs text-muted-foreground mt-0.5">{item.description}</p>
                      <span className="text-[10px] text-gold mt-1 block">{item.dueDate}</span>
                    </div>
                    <ChevronRight className="w-5 h-5 text-muted-foreground" />
                  </div>
                </button>
              ))}
            </div>
          </section>
        )}

        {/* Risk records */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium text-foreground">安全记录</h2>
            <button className="text-xs text-primary">查看全部</button>
          </div>
          <div className="bg-card rounded-2xl shadow-soft border border-border/50 overflow-hidden">
            {riskRecords.map((record, index) => (
              <div
                key={record.id}
                className={`px-4 py-4 flex items-start gap-3 ${
                  index !== riskRecords.length - 1 ? 'border-b border-border/30' : ''
                }`}
              >
                <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                  record.resolved ? 'bg-green-100' : 'bg-rose-soft'
                }`}>
                  <AlertTriangle className={`w-4 h-4 ${
                    record.resolved ? 'text-green-600' : 'text-rose'
                  }`} />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-medium text-foreground">{record.title}</h3>
                    {record.resolved && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-100 text-green-700">已处理</span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">{record.description}</p>
                  <span className="text-[10px] text-muted-foreground/70 mt-1 block">{record.time}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Notifications */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium text-foreground">审核通知</h2>
            <button className="text-xs text-primary">查看全部</button>
          </div>
          <div className="bg-card rounded-2xl shadow-soft border border-border/50 overflow-hidden">
            {notifications.map((notification, index) => (
              <div
                key={notification.id}
                className={`px-4 py-4 flex items-start gap-3 ${
                  index !== notifications.length - 1 ? 'border-b border-border/30' : ''
                }`}
              >
                <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
                  <FileText className="w-4 h-4 text-muted-foreground" />
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-medium text-foreground">{notification.title}</h3>
                  <p className="text-xs text-muted-foreground mt-0.5">{notification.description}</p>
                  <span className="text-[10px] text-muted-foreground/70 mt-1 block">{notification.time}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Help */}
        <div className="bg-blush/40 rounded-2xl p-4 text-center">
          <p className="text-sm text-taupe mb-2">遇到问题？</p>
          <button className="text-sm text-primary font-medium">联系客服支持</button>
        </div>
      </div>
    </div>
  )
}
