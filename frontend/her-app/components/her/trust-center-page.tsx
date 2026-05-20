'use client'

import { Shield, BadgeCheck, AlertTriangle, FileText, Clock, ChevronRight, CheckCircle, XCircle, Upload } from 'lucide-react'

interface TrustCenterPageProps {
  onStartVerification: () => void
}

const verificationStatus = {
  items: [
    { name: '身份认证', status: 'verified', description: '已通过实名认证' },
    { name: '学历认证', status: 'verified', description: '复旦大学 · 本科' },
    { name: '职业认证', status: 'pending', description: '审核中，预计1-2个工作日' },
    { name: '收入认证', status: 'unverified', description: '可选认证，提升可信度' },
  ],
}

const pendingItems = [
  { id: '1', title: '职业认证材料', description: '请补充在职证明或工牌照片', dueDate: '2024年3月15日前' },
]

const riskRecords = [
  { id: '1', title: '账号安全提醒', description: '检测到异地登录，请确认是否本人操作', time: '3天前', resolved: true },
]

const notifications = [
  { id: '1', title: '学历认证已通过', description: '你的学历信息已成功认证', time: '1天前' },
  { id: '2', title: '职业认证提交成功', description: '材料已提交，请耐心等待审核', time: '2天前' },
]

export default function TrustCenterPage({ onStartVerification }: TrustCenterPageProps) {
  const getStatusStyles = (status: string) => {
    if (status === 'verified') return { bg: 'bg-primary/10', text: 'text-primary', icon: 'text-primary' }
    if (status === 'pending') return { bg: 'bg-gold/10', text: 'text-gold', icon: 'text-gold' }
    return { bg: 'bg-secondary', text: 'text-muted-foreground', icon: 'text-muted-foreground' }
  }

  const getStatusIcon = (status: string) => {
    const styles = getStatusStyles(status)
    if (status === 'verified') return <CheckCircle className={`w-5 h-5 ${styles.icon}`} />
    if (status === 'pending') return <Clock className={`w-5 h-5 ${styles.icon}`} />
    return <XCircle className={`w-5 h-5 ${styles.icon}`} />
  }

  const getStatusText = (status: string) => {
    if (status === 'verified') return '已认证'
    if (status === 'pending') return '审核中'
    return '未认证'
  }

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
              <Shield className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h1 className="font-medium">信任中心</h1>
              <p className="text-xs text-muted-foreground">安全、透明、值得信赖</p>
            </div>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 pb-20">
        {/* Overall status */}
        <section className="bg-card border border-border rounded-xl p-4">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
              <BadgeCheck className="w-6 h-6 text-primary" />
            </div>
            <div>
              <h2 className="font-medium">可信度良好</h2>
              <p className="text-xs text-muted-foreground">3项已认证 · 1项审核中</p>
            </div>
          </div>
          <div className="grid grid-cols-4 gap-2">
            {verificationStatus.items.map((item, i) => {
              const styles = getStatusStyles(item.status)
              return (
                <div key={i} className={`text-center p-2 rounded-lg ${styles.bg}`}>
                  <div className="flex justify-center mb-1">{getStatusIcon(item.status)}</div>
                  <span className="text-[10px] text-muted-foreground">{item.name.slice(0, 2)}</span>
                </div>
              )
            })}
          </div>
        </section>

        {/* Verification items */}
        <section>
          <h2 className="text-sm font-medium mb-2">认证状态</h2>
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            {verificationStatus.items.map((item, i) => {
              const styles = getStatusStyles(item.status)
              return (
                <button
                  key={i}
                  onClick={item.status === 'unverified' ? onStartVerification : undefined}
                  className={`w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-secondary/50 ${
                    i !== verificationStatus.items.length - 1 ? 'border-b border-border' : ''
                  }`}
                >
                  {getStatusIcon(item.status)}
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{item.name}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${styles.bg} ${styles.text}`}>
                        {getStatusText(item.status)}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">{item.description}</p>
                  </div>
                  {item.status === 'unverified' && <ChevronRight className="w-4 h-4 text-muted-foreground" />}
                </button>
              )
            })}
          </div>
        </section>

        {/* Pending items */}
        {pendingItems.length > 0 && (
          <section>
            <h2 className="text-sm font-medium mb-2">待处理</h2>
            <div className="space-y-2">
              {pendingItems.map((item) => (
                <button key={item.id} onClick={onStartVerification} className="w-full bg-card border border-border rounded-xl p-3 text-left hover:border-primary/30 transition-colors">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-gold/10 flex items-center justify-center">
                      <Upload className="w-4 h-4 text-gold" />
                    </div>
                    <div className="flex-1">
                      <span className="text-sm font-medium">{item.title}</span>
                      <p className="text-xs text-muted-foreground">{item.description}</p>
                      <span className="text-[10px] text-gold">{item.dueDate}</span>
                    </div>
                    <ChevronRight className="w-4 h-4 text-muted-foreground" />
                  </div>
                </button>
              ))}
            </div>
          </section>
        )}

        {/* Risk records */}
        <section>
          <h2 className="text-sm font-medium mb-2">安全记录</h2>
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            {riskRecords.map((record, i) => (
              <div key={record.id} className={`px-4 py-3 flex items-center gap-3 ${i !== riskRecords.length - 1 ? 'border-b border-border' : ''}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center ${record.resolved ? 'bg-primary/10' : 'bg-rose/10'}`}>
                  <AlertTriangle className={`w-4 h-4 ${record.resolved ? 'text-primary' : 'text-rose'}`} />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{record.title}</span>
                    {record.resolved && <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">已处理</span>}
                  </div>
                  <p className="text-xs text-muted-foreground">{record.description}</p>
                  <span className="text-[10px] text-muted-foreground">{record.time}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Notifications */}
        <section>
          <h2 className="text-sm font-medium mb-2">审核通知</h2>
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            {notifications.map((n, i) => (
              <div key={n.id} className={`px-4 py-3 flex items-center gap-3 ${i !== notifications.length - 1 ? 'border-b border-border' : ''}`}>
                <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
                  <FileText className="w-4 h-4 text-muted-foreground" />
                </div>
                <div className="flex-1">
                  <span className="text-sm font-medium">{n.title}</span>
                  <p className="text-xs text-muted-foreground">{n.description}</p>
                  <span className="text-[10px] text-muted-foreground">{n.time}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        <div className="bg-secondary rounded-xl p-4 text-center">
          <p className="text-sm text-muted-foreground mb-1">遇到问题？</p>
          <button className="text-sm text-primary font-medium">联系客服支持</button>
        </div>
      </div>
    </div>
  )
}
