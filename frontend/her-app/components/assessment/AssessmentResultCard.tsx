'use client'

import { useState, useMemo, useEffect } from 'react'
import { Share2, Check, Star, Trophy } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { type AssessmentType } from './assessment-themes'

// MBTI type nicknames
const TYPE_NICKNAMES: Record<string, string> = {
  INTJ: '策略家',
  INTP: '逻辑学家',
  ENTJ: '指挥官',
  ENTP: '辩论家',
  INFJ: '提倡者',
  INFP: '调停者',
  ENFJ: '主人公',
  ENFP: '竞选者',
  ISTJ: '物流师',
  ISFJ: '守卫者',
  ESTJ: '总经理',
  ESFJ: '执政官',
  ISTP: '鉴赏家',
  ISFP: '探险家',
  ESTP: '企业家',
  ESFP: '表演者',
}

// Attachment style type nicknames (ECR quadrant labels)
const ATTACHMENT_NICKNAMES: Record<string, string> = {
  secure: '稳定靠近型',
  anxious: '高敏确认型',
  avoidant: '边界后撤型',
  fearful: '拉扯矛盾型',
}

const MBTI_LABEL_PRESETS: Record<string, string[]> = {
  ENFJ: [
    '爹妈系纯爱战神',
    '恋爱脑大祭司：容易母爱/父爱瞬间泛滥，看对方总觉得对方“生活不能自理”。',
    '情绪消防员：冲突时坚信“先灭火，再修房子”，必须先抱抱揉揉，再聊对错。',
    '满分捧哏：自带全方位无死角夸夸群功能，能给对方提供核动力级别的鼓励。',
    '当代纯爱战神：认定一个人直接开启“执子之手，与子偕老”的沉浸式剧本。',
  ],
  ENFP: [
    '快乐小狗 / 撤回狂魔',
    '分享欲晚期患者：路过的狗长得滑稽都要拍下来发给对方，消息轰炸机。',
    '一秒脑补剧场：冷淡一秒，心里连孩子跟谁姓、离婚财产怎么分都想好了。',
    '约会气氛组组长：只要有Ta在，哪怕去民政局排队都能变成游乐场蹦迪。',
    '上头风向标：微信置顶的含金量全看Ta当下对你的上头程度。',
  ],
  ENTJ: [
    '恋爱合伙人 / 霸总本总',
    'KPI式恋爱：恋爱要有规划和季度复盘，不接受没有未来的无意义内耗。',
    '问题粉碎机：冲突时冷酷化身无情AI，倾向“先解决问题，情绪是什么能吃吗”。',
    '特约赞助商：自然倾向用“清空购物车”或“送实用资产”来粗暴表达爱意。',
    '关系推土机：目标明确，带节奏狂魔，会推着对方和关系大步向前走。',
  ],
  ENTP: [
    '傲娇杠精 / 乐子人',
    '杠精甜心：嘴上在疯狂挑衅、把吵架当辩论赛，其实心里在疯狂摇尾巴撒娇。',
    '高智商挑剔狂：需要智力共鸣，如果没有思想碰撞，Ta会觉得像在陪小学生写作业。',
    '新型浪漫家：聊天很有趣，能带你体验100种不重样的人生新玩法。',
    '嘴硬心软代言人：虽然嘴上爱怼，但认定你之后，别人多说你一句Ta能跟人拼命。',
  ],
  ESFJ: [
    '全能型保姆恋爱',
    '细节监控器：细节控天花板，连你明天穿什么、带不带伞、吃不吃香菜都规划好了。',
    '夸夸渴望者：极度需要情绪价值和被肯定，付出后需要对方大声说“你好棒”。',
    '春风化雨流：很会照顾对方，生活细节拉满，妥妥的“24小时贴身暖宝宝”。',
    '契约精神狂：认定一个人就会拿出写进教科书般的认真态度去经营。',
  ],
  ESFP: [
    '及时行乐小陀螺',
    '约会蹦迪炸弹：及时行乐的老玩家，有Ta在的约会永远不会无聊。',
    '金鱼的记忆：吵架只要给个台阶、带Ta去吃顿火锅，瞬间失忆，绝不记仇。',
    '快乐制造机：活在当下，天塌下来当被盖，能给对方提供高纯度的快乐。',
    '睁眼瞎式乐观：太乐天派，有时候会选择性逃避现实中的硬伤和长远问题。',
  ],
  ESTJ: [
    '教导主任式恋爱',
    '迟到报警器：时间管理狂魔，约会迟到5分钟直接在Ta心里触发红色警报。',
    '规矩第一人：冲突时倾向先对表、讲规矩，复盘谁的责任（成熟后会克制住先哄人）。',
    '恋爱面试官：条框清晰，手握硬性标准，知道自己要找什么样的人生伴侣。',
    '硬核军师：专治各种矫情，能一针见血帮对方理清思路、解决骨头问题。',
  ],
  ESTP: [
    '直球行动派 / 线下单挑王',
    '网聊绝缘体：微信聊100句不如立刻出门见面，讨厌隔着屏幕猜心思。',
    '直球重工业者：不懂弯弯绕绕，爱就大声说，恨就当面锣对面鼓。',
    '速战速决派：冲突时喜欢当场解决，绝不拖泥带水，没有冷战的基因。',
    '执行力天花板：说好的约会、旅行，立马订票，能带你体验最顶级的感官刺激。',
  ],
  INFP: [
    '易碎纯爱小蝴蝶',
    '国家级保护动物：出了名的玻璃心与纯爱战神结合体，需要轻拿轻放。',
    '回消息侦探：回消息慢5分钟，已经在心里复盘了10遍“Ta是不是不爱我了”。',
    '拒绝被重装系统：冲突时先内耗情绪，极度需要被理解灵性和内核，拒绝被说教。',
    '献祭流选手：认定一个人会把防御全卸掉，非常专一，付出多到让人心疼。',
  ],
  INFJ: [
    '精神导师 / 读心术大师',
    '人形测谎仪：一眼看穿你的小心思，表面温柔微笑，内心在评估你的灵魂深度。',
    '高阶读心术：冲突时能精准狙击你的情绪痛点，但也擅长自我内耗。',
    '精神神交狂：不看重物质，更看重灵魂是否共鸣、三观是否契合。',
    '人间蒸发术：如果觉得你不合适，会默默扣分，直到最后一天无声无息地彻底消失。',
  ],
  INTJ: [
    '内心戏满分的小黑屋所长',
    '阎王扣分表：表面不动如山甚至高冷，内心已经默默掏出扣分表把你复盘了个遍。',
    '逻辑怪兽：吵架偏好复盘因果关系和逻辑链条，“多喝热水”在Ta眼里是无用垃圾信息。',
    '硬核浪漫：爱是终极解决方案，浪漫绝缘体成熟后，会把“为你规划人生防线”当成最深沉的爱。',
  ],
  INTP: [
    '人间清醒的断电猫咪',
    '人形错题本：冲突时自带死理性派滤镜，倾向先分析逻辑漏洞，吵架喜欢讲道理。',
    '极度需要充电：社交能量条极短，恋爱也必须有Ta专属的“绝对闭关小黑屋”。',
    '军师型表达：表达爱的方式不是甜言蜜语，而是帮你分析、解决Ta认为重要的人生课题。',
    '默默无闻款：认定了就会极其稳定地默默付出，虽然看起来还是冷冰冰的。',
  ],
  ISFJ: [
    '隐忍流暖水瓶',
    '隐忍小账本：冲突时表面顺从说“没事”，其实心里已经拿小本本默默记了一大笔账。',
    '安全感黑洞：不确定对方心意时会极度焦虑，需要对方不断用行动填满安全感。',
    '不开口的闷葫芦：不容易主动表达需求，玩“你猜你猜你猜猜猜”，容易委屈自己。',
    '万年老树根：极其专一和稳定，认定一个人就是奔着一辈子安稳日子去的。',
  ],
  ISFP: [
    '文艺风微醺艺术家',
    '氛围感大师：极度看重约会的情调、审美与背景音乐，生活必须有艺术感。',
    '嘴笨星人：冲突时心里难受得要死，但一句话也说不出来，只想逃进自己的世界。',
    '情绪海绵：共情能力极强，能敏锐感受到你的气压变化，但也容易被你的坏情绪吸干。',
    '求顺毛驴：需要极多的赞美、欣赏和偏爱，不然就会缩回壳里觉得自己委屈。',
  ],
  ISTJ: [
    '铁面无私的盖章机',
    '行走的法律条文：说到必须做到，雷打不动，讨厌一切意料之外的变数。',
    '冷酷质检员：冲突时倾向先复盘到底是谁的错，靠谱和责任感就是Ta的终极浪漫。',
    '老干部风骨：太稳定有时候显得像在和长辈谈恋爱，不够有趣，但绝对不会出轨。',
  ],
  ISTP: [
    '独行侠 / 冷暴力天花板',
    '冷战专业户：冲突时倾向开启“别理我、断联、玩消失”的自闭三连。',
    '野生保护动物：需要极大的个人野生空间，试图拴住Ta的线随时可能断掉。',
    '修灯泡流恋爱：不会说好听的，表达爱的方式是默默帮你搞定所有坏掉的家电和难题。',
  ],
}

const ATTACHMENT_LABEL_PRESETS: Record<string, string[]> = {
  secure: [
    '稳稳接住派',
    '情绪防抖器：对方一时冷一点热一点，你通常不会立刻脑补成感情地震。',
    '亲密不卡壳：该靠近能靠近，该独处能独处，不太需要靠拉扯证明在乎。',
    '修复速度在线：闹别扭时更容易把注意力放回解决问题，不太爱无限上纲。',
    '关系松弛感选手：不会天天查岗，但也不是失踪人口，主打一个稳定在场。',
  ],
  anxious: [
    '回应雷达开很满',
    '已读显微镜：对方语气轻一点重一点，你都能第一时间捕捉到风向变化。',
    '确认感刚需户：越在意一个人，越希望关系别靠猜，最好能说清楚一点。',
    '忽冷忽热过敏体质：最怕前一天很热络，后一天像客服下线，特别消耗。',
    '脑内小剧场编导：线索一模糊，脑子可能已经先把关系走向预演了三遍。',
  ],
  avoidant: [
    '先缓一下派',
    '亲密防过载系统：不是不想靠近，是关系一旦太快太满，你会先想降噪。',
    '边界感高敏人群：越被追着问、追着贴，越容易触发你想后撤的本能。',
    '沉默自保型选手：压力一上来，容易先把情绪收回去，不一定会当场说。',
    '慢热通关模式：要先确认安全和节奏合适，你才会愿意把真实自己打开。',
  ],
  fearful: [
    '想靠近也想自保',
    '拉扯感双开模式：一边很想确认对方在不在，一边又怕太近会把自己卷进去。',
    '安全感和空间感都要：少一个你都容易难受，多一点少一点都可能触发警报。',
    '反复横跳不是作：很多时候不是故意，是想靠近和想自保同时在线。',
    '高难度相处体质：最需要那种既稳定又不逼近的人，不然真的很容易累。',
  ],
}

function normalizeTypeCode(typeCode?: string) {
  return typeCode?.trim().toLowerCase()
}

function parseLabelDetail(label: string) {
  const match = label.match(/^([^：:]+)[：:]\s*(.+)$/)
  if (!match) {
    return { title: label.trim(), detail: '' }
  }
  return { title: match[1].trim(), detail: match[2].trim() }
}

interface DimensionRow {
  key: string
  name: string
  score: number
  level: 'high' | 'medium' | 'low'
  trait: string
}

interface ExtremeTag {
  tag: string
  description: string
}

interface InterpretationData {
  summary: string
  love_style?: string
  match_suggestions?: string[]
  relationship_drive?: string
  triggers?: string
  stabilizers?: string
  common_misread?: string
  communication_advice?: string
  card_tip?: string
  fit_people?: string[]
  friction_people?: string[]
  ecr_basis?: string[]
  quadrant_label?: string
  disclaimer?: string
  extreme_tags?: ExtremeTag[]
}

interface QuadrantData {
  x_key: string
  x_name: string
  x_score: number
  y_key: string
  y_name: string
  y_score: number
  type_code: string
  type_name: string
  quadrants: Record<string, {
    type_code: string
    label: string
  }>
}

interface ResultData {
  type_code?: string
  scores: Record<string, number>
  dimension_rows?: DimensionRow[]
  quadrant?: QuadrantData
  labels?: string[]  // 改为可选，因为后端可能不返回
  interpretation_data?: InterpretationData
  reward: string
  assessment_id: string
}

// Dimension label mapping with explanations (matching backend keys)
const DIMENSION_LABELS: Record<string, { high: string; low: string }> = {
  // MBTI dimensions
  'ei': { high: '外向', low: '内向' },
  'sn': { high: '实感', low: '直觉' },  // 修复: S是高分(>=50),代表实感/关注现实细节; N是低分(<50),代表直觉/关注可能性
  'tf': { high: '思考', low: '情感' },
  'jp': { high: '判断', low: '感知' },
  // Attachment dimensions
  'anxiety': { high: '回应敏感', low: '稳定感较强' },
  'avoidance': { high: '边界警觉', low: '靠近自如' },
  // Big Five dimensions
  'openness': { high: '开放性较高', low: '开放性较低' },
  'conscientiousness': { high: '尽责性较高', low: '尽责性较低' },
  'extraversion': { high: '外向性较高', low: '外向性较低' },
  'agreeableness': { high: '宜人性较高', low: '宜人性较低' },
  'neuroticism': { high: '神经质较高', low: '神经质较低' },
  // Sternberg dimensions
  'intimacy': { high: '深入靠近', low: '仍在保留' },
  'passion': { high: '火花强烈', low: '克制观察' },
  'commitment': { high: '长期投入', low: '暂不绑定' },
}

// Radar Chart Component
function RadarChart({
  dimensions = [],
  size = 280,
  assessmentType,
}: {
  dimensions?: DimensionRow[]
  size?: number
  assessmentType?: AssessmentType
}) {
  const center = size / 2
  const maxRadius = (size / 2) - 50
  const levels = 4

  // Get theme color for the chart
  const chartColorClass = assessmentType === 'attachment_style' 
    ? 'text-coral' 
    : 'text-primary'

  if (!dimensions.length) {
    return (
      <div className="flex h-[280px] items-center justify-center rounded-3xl border border-dashed border-border text-sm text-muted-foreground">
        {"暂无雷达图数据"}
      </div>
    )
  }

  // Calculate points for each dimension (memoized)
  const points = useMemo(() => {
    return dimensions.map((dim, i) => {
      const angle = (Math.PI * 2 * i) / dimensions.length - Math.PI / 2
      const radius = (dim.score / 100) * maxRadius
      return {
        x: center + Math.cos(angle) * radius,
        y: center + Math.sin(angle) * radius,
        angle,
        dim,
      }
    })
  }, [dimensions, center, maxRadius])

  // Create polygon path
  const polygonPath = useMemo(() => {
    return points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ') + ' Z'
  }, [points])

  // Calculate label positions based on actual SVG coordinates (memoized with collision detection)
  const labelPositions = useMemo(() => {
    const positions = dimensions.map((dim, i) => {
      const angle = (Math.PI * 2 * i) / dimensions.length - Math.PI / 2
      const labelRadius = maxRadius + 35
      const x = center + Math.cos(angle) * labelRadius
      const y = center + Math.sin(angle) * labelRadius
      return { x, y, angle, key: dim.key }
    })
    
    // Simple collision detection and adjustment
    const minDistance = 40
    for (let i = 0; i < positions.length; i++) {
      for (let j = i + 1; j < positions.length; j++) {
        const dx = positions[j].x - positions[i].x
        const dy = positions[j].y - positions[i].y
        const distance = Math.sqrt(dx * dx + dy * dy)
        
        if (distance < minDistance) {
          // Push labels apart slightly
          const adjustment = (minDistance - distance) / 2
          const angle = Math.atan2(dy, dx)
          positions[i].x -= Math.cos(angle) * adjustment
          positions[i].y -= Math.sin(angle) * adjustment
          positions[j].x += Math.cos(angle) * adjustment
          positions[j].y += Math.sin(angle) * adjustment
        }
      }
    }
    
    return positions
  }, [dimensions, center, maxRadius])

  return (
    <div className="relative will-change-transform" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="absolute top-0 left-0">
        {/* Background grid circles */}
        {Array.from({ length: levels }).map((_, i) => {
          const r = ((i + 1) / levels) * maxRadius
          return (
            <circle
              key={i}
              cx={center}
              cy={center}
              r={r}
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-border"
              strokeDasharray={i < levels - 1 ? '2 4' : 'none'}
            />
          )
        })}

        {/* Axis lines */}
        {points.map((p, i) => {
          const angle = (Math.PI * 2 * i) / dimensions.length - Math.PI / 2
          const endX = center + Math.cos(angle) * maxRadius
          const endY = center + Math.sin(angle) * maxRadius
          return (
            <line
              key={i}
              x1={center}
              y1={center}
              x2={endX}
              y2={endY}
              stroke="currentColor"
              strokeWidth="1"
              className="text-border"
            />
          )
        })}

        {/* Data polygon */}
        <path
          d={polygonPath}
          fill="currentColor"
          fillOpacity="0.15"
          stroke="currentColor"
          strokeWidth="2"
          className={chartColorClass}
        />

        {/* Data points */}
        {points.map((p, i) => (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r="4"
            fill="currentColor"
            className={chartColorClass}
          />
        ))}

        {/* Center point */}
        <circle
          cx={center}
          cy={center}
          r="3"
          fill="currentColor"
          className="text-muted-foreground"
        />
      </svg>

      {/* External dimension labels with explanations */}
      {dimensions.map((dim, i) => {
        const pos = labelPositions[i]
        const dimLabel = DIMENSION_LABELS[dim.key] || { high: dim.key, low: dim.key }
        const isHigh = dim.score >= 50

        return (
          <div
            key={i}
            className="absolute flex flex-col items-center justify-center"
            style={{
              left: pos.x,
              top: pos.y,
              transform: 'translate(-50%, -50%)',
              width: '70px',
            }}
          >
            <div className="text-xs font-medium text-foreground mb-0.5 text-center leading-tight">
              {dim.name}
            </div>
            <div className="text-[10px] text-muted-foreground text-center leading-tight">
              {isHigh ? dimLabel.high : dimLabel.low}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function AttachmentQuadrantChart({
  quadrant,
}: {
  quadrant?: QuadrantData
}) {
  if (!quadrant) {
    return (
      <div className="flex h-[280px] items-center justify-center rounded-3xl border border-dashed border-border text-sm text-muted-foreground">
        {"暂无坐标图数据"}
      </div>
    )
  }

  const xPercent = Math.max(0, Math.min(100, quadrant.x_score))
  const yPercent = Math.max(0, Math.min(100, quadrant.y_score))
  const pointLeft = `${xPercent}%`
  const pointTop = `${100 - yPercent}%`

  const labels = quadrant.quadrants

  return (
    <div className="rounded-[28px] border border-coral/15 bg-gradient-to-br from-coral/8 via-card to-rose/10 p-4">
      <div className="mb-3 text-center">
        <div className="text-xs uppercase tracking-[0.24em] text-coral/80">ECR 坐标</div>
        <div className="mt-1 text-sm text-muted-foreground">
          {quadrant.y_name} {Math.round(quadrant.y_score)} · {quadrant.x_name} {Math.round(quadrant.x_score)}
        </div>
      </div>

      <div className="relative mx-auto h-[280px] max-w-[280px]">
        <div className="absolute inset-0 rounded-[24px] bg-gradient-to-br from-coral/6 via-transparent to-coral/6" />

        <div className="absolute left-1/2 top-2 -translate-x-1/2 text-[11px] text-muted-foreground">
          高{quadrant.y_name}
        </div>
        <div className="absolute bottom-2 left-1/2 -translate-x-1/2 text-[11px] text-muted-foreground">
          低{quadrant.y_name}
        </div>
        <div className="absolute left-2 top-1/2 -translate-y-1/2 text-[11px] text-muted-foreground">
          低{quadrant.x_name}
        </div>
        <div className="absolute right-2 top-1/2 -translate-y-1/2 text-[11px] text-muted-foreground">
          高{quadrant.x_name}
        </div>

        <div className="absolute inset-6 rounded-[20px] border border-border/70 bg-card/70" />
        <div className="absolute inset-6">
          <div className="absolute left-1/2 top-0 h-full w-px bg-border" />
          <div className="absolute left-0 top-1/2 h-px w-full bg-border" />

          <div className="absolute left-[12%] top-[12%] max-w-[88px] text-[12px] leading-tight text-muted-foreground">
            {labels.top_left?.label || '拉扯矛盾型'}
          </div>
          <div className="absolute right-[10%] top-[12%] max-w-[88px] text-right text-[12px] leading-tight text-muted-foreground">
            {labels.top_right?.label || '高敏确认型'}
          </div>
          <div className="absolute bottom-[12%] left-[12%] max-w-[88px] text-[12px] leading-tight text-muted-foreground">
            {labels.bottom_left?.label || '稳定靠近型'}
          </div>
          <div className="absolute bottom-[12%] right-[10%] max-w-[88px] text-right text-[12px] leading-tight text-muted-foreground">
            {labels.bottom_right?.label || '边界后撤型'}
          </div>

          <div
            className="absolute z-20 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-coral shadow-[0_0_0_6px_rgba(238,111,101,0.18)]"
            style={{ left: pointLeft, top: pointTop }}
          />
        </div>
      </div>
    </div>
  )
}

function getTypeNickname(typeCode?: string, assessmentType?: AssessmentType): string {
  if (!typeCode) {
    return ''
  }

  const normalizedTypeCode = normalizeTypeCode(typeCode)
  if (assessmentType === 'attachment_style') {
    return ATTACHMENT_NICKNAMES[normalizedTypeCode || ''] || ''
  }
  if (assessmentType === 'big_five' || assessmentType === 'sternberg_triangular_love') {
    return ''
  }
  return TYPE_NICKNAMES[typeCode.trim()] || ''
}

function resolveDisplayType(typeCode?: string, assessmentType?: AssessmentType): string {
  const rawTypeCode = typeCode?.trim()
  const normalizedTypeCode = normalizeTypeCode(typeCode)

  if (assessmentType === 'attachment_style') {
    return ATTACHMENT_NICKNAMES[normalizedTypeCode || ''] || rawTypeCode || '--'
  }
  if (assessmentType === 'big_five') {
    return 'BIG FIVE'
  }
  if (assessmentType === 'sternberg_triangular_love') {
    return '三元结构'
  }

  if (rawTypeCode && TYPE_NICKNAMES[rawTypeCode]) {
    return rawTypeCode
  }

  if (normalizedTypeCode && ATTACHMENT_NICKNAMES[normalizedTypeCode]) {
    return ATTACHMENT_NICKNAMES[normalizedTypeCode]
  }

  return rawTypeCode || '--'
}

export function AssessmentResultCard({
  data,
  onAddLabels,
  onShare,
  assessmentType,
}: {
  data: ResultData
  onAddLabels?: (selectedLabels: string[]) => Promise<void>
  onShare?: () => void
  assessmentType?: AssessmentType
}) {
  const [isAdding, setIsAdding] = useState(false)
  const [addedLabels, setAddedLabels] = useState<Set<string>>(new Set())
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean
    label: string
  }>({ open: false, label: '' })
  const [isRevealed, setIsRevealed] = useState(false)
  
  // Trigger reveal animation on mount
  useEffect(() => {
    const revealTimer = setTimeout(() => setIsRevealed(true), 100)
    return () => {
      clearTimeout(revealTimer)
    }
  }, [])

  const typeNickname = getTypeNickname(data.type_code, assessmentType)
  const safeTypeCode = resolveDisplayType(data.type_code, assessmentType)
  const isMbti = !assessmentType || assessmentType === 'mbti_16'
  const isAttachment = assessmentType === 'attachment_style'
  const isSternberg = assessmentType === 'sternberg_triangular_love'
  const isBigFive = assessmentType === 'big_five'
  const displayLabels = useMemo(() => {
    if (isMbti) {
      return MBTI_LABEL_PRESETS[data.type_code?.trim() || ''] || data.labels || []
    }
    if (isAttachment) {
      return ATTACHMENT_LABEL_PRESETS[normalizeTypeCode(data.type_code) || ''] || data.labels || []
    }
    return data.labels || []
  }, [data.labels, data.type_code, isAttachment, isMbti])
  const interpretation = data.interpretation_data

  // Theme-based colors
  const extremeTagBg = assessmentType === 'attachment_style'
    ? 'bg-coral-soft/60 border-coral/20'
    : isBigFive
      ? 'bg-sage-soft/60 border-sage/20'
      : isSternberg
        ? 'bg-amber-soft/60 border-amber/20'
        : 'bg-rose-soft/60 border-rose/20'
  
  const extremeTagIcon = assessmentType === 'attachment_style'
    ? 'text-coral'
    : isBigFive
      ? 'text-sage'
      : isSternberg
        ? 'text-amber'
        : 'text-rose'

  const handleLabelClick = (label: string) => {
    const { title } = parseLabelDetail(label)
    if (!onAddLabels || addedLabels.has(title) || isAdding) {
      return
    }
    setConfirmDialog({ open: true, label: title })
  }

  const handleConfirmAddLabel = async () => {
    const label = confirmDialog.label
    if (!onAddLabels || addedLabels.has(label)) return

    setIsAdding(true)
    setConfirmDialog({ open: false, label: '' })
    try {
      await onAddLabels([label])
      setAddedLabels((prev) => new Set(prev).add(label))
    } finally {
      setIsAdding(false)
    }
  }

  const handleCancelAddLabel = () => {
    setConfirmDialog({ open: false, label: '' })
  }

  // Selected label colors
  const selectedLabelClass = assessmentType === 'attachment_style'
    ? 'bg-coral/15 border-coral/40'
    : isBigFive
      ? 'bg-sage/15 border-sage/40'
      : isSternberg
        ? 'bg-amber/15 border-amber/40'
        : 'bg-primary/15 border-primary/40'

  return (
    <>
      <div className={cn(
        'rounded-3xl border border-border bg-card p-6 shadow-sm overflow-y-auto max-h-[70vh] scroll-fade-bottom',
        isRevealed ? 'animate-score-reveal' : 'opacity-0 scale-90'
      )}>
        {/* Trophy icon */}
        <div className="flex justify-center mb-4">
          <div className={cn(
            'w-16 h-16 rounded-full flex items-center justify-center',
            assessmentType === 'attachment_style'
              ? 'bg-coral/15'
              : isBigFive
                ? 'bg-sage/15'
                : isSternberg
                  ? 'bg-amber/15'
                  : 'bg-primary/15'
          )}>
            <Trophy className={cn(
              'w-8 h-8',
              assessmentType === 'attachment_style'
                ? 'text-coral'
                : isBigFive
                  ? 'text-sage'
                  : isSternberg
                    ? 'text-amber'
                    : 'text-primary'
            )} />
          </div>
        </div>
        
        {/* Header with share button */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex-1 text-center">
            <div className={cn(
              'text-xs uppercase tracking-widest mb-2',
              assessmentType === 'attachment_style'
                ? 'text-coral'
                : isBigFive
                  ? 'text-sage'
                  : isSternberg
                    ? 'text-amber'
                    : 'text-muted-foreground'
            )}>
              {"测评结果"}
            </div>
            <div className="flex items-baseline justify-center gap-2">
              <span className={cn(
                'text-4xl font-bold tracking-tight animate-number-roll',
                assessmentType === 'attachment_style'
                  ? 'text-coral'
                  : isBigFive
                    ? 'text-sage'
                    : isSternberg
                      ? 'text-amber'
                      : ''
              )}>
                {safeTypeCode}
              </span>
            </div>
            {typeNickname && typeNickname !== safeTypeCode && !isMbti && (
              <div className="text-sm text-muted-foreground mt-1">{typeNickname}</div>
            )}
          </div>
        </div>
        
        {/* Share button */}
        {onShare && (
          <div className="flex justify-center mb-4">
            <button
              onClick={onShare}
              className={cn(
                'flex items-center gap-2 px-4 py-2 rounded-full text-sm transition-all touch-target active:scale-95',
                assessmentType === 'attachment_style'
                  ? 'bg-coral/10 text-coral hover:bg-coral/20'
                  : isBigFive
                    ? 'bg-sage/10 text-sage hover:bg-sage/20'
                    : isSternberg
                      ? 'bg-amber/10 text-amber hover:bg-amber/20'
                      : 'bg-secondary text-muted-foreground hover:bg-secondary/80'
              )}
            >
              <Share2 className="w-4 h-4" />
              {"分享结果"}
            </button>
          </div>
        )}

      {/* Extreme Tags */}
      {data.interpretation_data?.extreme_tags && data.interpretation_data.extreme_tags.length > 0 && (
        <div className="mb-5 space-y-2">
          {isMbti && (
            <div className="text-xs text-muted-foreground">
              {"以下标签为产品化表达，帮助你快速记忆，不属于 MBTI 官方术语。"}
            </div>
          )}
          {assessmentType === 'attachment_style' ? (
            <div className="flex flex-wrap gap-2">
              {data.interpretation_data.extreme_tags.map((extreme, idx) => (
                <div
                  key={idx}
                  className={cn(
                    'inline-flex items-center gap-2 rounded-full border px-3 py-1.5',
                    extremeTagBg,
                  )}
                >
                  <Star className={cn('w-3.5 h-3.5 shrink-0', extremeTagIcon)} fill="currentColor" />
                  <span className={cn('text-xs font-medium', extremeTagIcon)}>{extreme.tag}</span>
                </div>
              ))}
            </div>
          ) : (
            <>
              {data.interpretation_data.extreme_tags.map((extreme, idx) => (
                <div
                  key={idx}
                  className={cn(
                    'flex items-center gap-2 rounded-2xl border px-4 py-2.5',
                    extremeTagBg
                  )}
                >
                  <Star className={cn('w-4 h-4 shrink-0', extremeTagIcon)} fill="currentColor" />
                  <div>
                    <span className={cn('font-medium text-sm', extremeTagIcon)}>{extreme.tag}</span>
                    <span className="ml-2 text-xs text-muted-foreground">{extreme.description}</span>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {/* Chart */}
      <div className="my-6 relative">
        {assessmentType === 'attachment_style' ? (
          <AttachmentQuadrantChart quadrant={data.quadrant} />
        ) : (
          <RadarChart 
            dimensions={data.dimension_rows} 
            size={280} 
            assessmentType={assessmentType}
          />
        )}
      </div>

      {interpretation && !isMbti && !isBigFive && !isSternberg && (
        <div className="mb-5 space-y-3">
          <div className="rounded-2xl bg-secondary/40 px-4 py-3">
            <div className="text-xs text-muted-foreground mb-1">核心解释</div>
            <p className="text-sm leading-relaxed text-foreground/90">{interpretation.summary}</p>
          </div>
          {interpretation.love_style && (
            <div className="rounded-2xl bg-secondary/30 px-4 py-3">
              <div className="text-xs text-muted-foreground mb-1">怎么读这份结果</div>
              <p className="text-sm leading-relaxed text-foreground/85">{interpretation.love_style}</p>
            </div>
          )}
          {!!interpretation.match_suggestions?.length && (
            <div className="rounded-2xl bg-secondary/30 px-4 py-3">
              <div className="text-xs text-muted-foreground mb-2">阅读提示</div>
              <div className="space-y-2">
                {interpretation.match_suggestions.map((item) => (
                  <p key={item} className="text-sm leading-relaxed text-foreground/85">{item}</p>
                ))}
              </div>
            </div>
          )}
          {interpretation.disclaimer && (
            <div className="rounded-2xl border border-border px-4 py-3">
              <div className="text-xs text-muted-foreground mb-1">依据说明</div>
              <p className="text-xs leading-relaxed text-muted-foreground">{interpretation.disclaimer}</p>
            </div>
          )}
        </div>
      )}

      {/* Labels Selection */}
      <div className="mb-5">
        <div className="text-xs text-muted-foreground mb-2.5">
          {isMbti ? "你的个性标签（点击添加到我的标签）：" : "你的恋爱标签（点击添加到我的标签）："}
        </div>
          {isAttachment && (
            <div className="text-xs text-muted-foreground mb-2">
              {"以下标签是产品化的人话翻译，帮助你更快记住自己的相处倾向。"}
            </div>
          )}
          {isBigFive && (
            <div className="text-xs text-muted-foreground mb-2">
              {"大五本质上是连续维度，这里的标签是对高低分组合的人话摘要。"}
            </div>
          )}
          {isSternberg && (
            <div className="text-xs text-muted-foreground mb-2">
              {"以下标签直接对应三元论的三条分数高低，是结构摘要，不是原理论里的固定爱情类型判定。"}
            </div>
          )}
        <div className="flex flex-wrap gap-2">
          {displayLabels.map((label) => {
            const { title } = parseLabelDetail(label)
            const isAdded = addedLabels.has(title)

            return (
              <button
                key={label}
                onClick={() => handleLabelClick(label)}
                disabled={isAdded || isAdding || !onAddLabels}
                className={cn(
                  'rounded-full px-3 py-1.5 text-xs cursor-pointer transition-all touch-target active:scale-95',
                  isAdded
                    ? cn(selectedLabelClass, 'border text-foreground')
                    : 'bg-secondary border border-transparent text-muted-foreground hover:bg-secondary/80 hover:border-border',
                  (isAdded || isAdding || !onAddLabels) && 'opacity-60'
                )}
              >
                {isAdded ? (
                  <span className="flex items-center gap-1">
                    <Check className="w-3 h-3" />
                    {title}
                  </span>
                ) : (
                  title
                )}
              </button>
            )
          })}
          {displayLabels.length === 0 && (
            <div className="text-xs text-muted-foreground italic">
              {"暂无标签数据"}
            </div>
          )}
        </div>
      </div>

      </div>

      <ConfirmDialog
        open={confirmDialog.open}
        title="添加标签"
        message={`是否将「${confirmDialog.label}」添加为我的标签？`}
        confirmText="添加"
        cancelText="暂不添加"
        onConfirm={handleConfirmAddLabel}
        onCancel={handleCancelAddLabel}
      />
    </>
  )
}
