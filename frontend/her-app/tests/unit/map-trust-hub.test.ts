import { describe, expect, it } from 'vitest'
import {
  mapTrustHubPendingActions,
  mapTrustHubVerificationItems,
  normalizeTrustVerificationStatus,
  trustVerificationProgress,
} from '@/lib/trust/map-trust-hub'

describe('map-trust-hub', () => {
  it('normalizes verification statuses', () => {
    expect(normalizeTrustVerificationStatus('approved')).toBe('verified')
    expect(normalizeTrustVerificationStatus('under_review')).toBe('pending')
    expect(normalizeTrustVerificationStatus('rejected')).toBe('action_required')
    expect(normalizeTrustVerificationStatus('unknown')).toBe('unverified')
  })

  it('maps trust hub items to view models', () => {
    const items = mapTrustHubVerificationItems([
      { title: '学历认证', status: 'under_review', status_label: '审核中' },
      { title: '职业认证', status: 'approved' },
    ])
    expect(items).toEqual([
      { name: '学历认证', status: 'pending', statusText: '审核中', description: '审核中', detail: undefined },
      { name: '职业认证', status: 'verified', statusText: '已认证', description: '等待进一步处理', detail: undefined },
    ])
  })

  it('maps rejected verification items to action required', () => {
    const items = mapTrustHubVerificationItems([
      { title: '学历认证', status: 'rejected', status_label: '已驳回', failure_reason: '证书信息与填写不一致' },
    ])
    expect(items).toEqual([
      {
        name: '学历认证',
        status: 'action_required',
        statusText: '已驳回',
        description: '已驳回',
        detail: '证书信息与填写不一致',
      },
    ])
  })

  it('computes verification progress', () => {
    const progress = trustVerificationProgress([
      { name: 'a', status: 'verified', statusText: '已认证', description: '' },
      { name: 'b', status: 'pending', statusText: '审核中', description: '' },
    ])
    expect(progress).toEqual({ verifiedCount: 1, total: 2, progress: 50 })
  })

  it('maps pending actions from non-verified items', () => {
    const actions = mapTrustHubPendingActions([
      { item_id: '1', title: '补充学历', status: 'pending', support_hint: '上传证书' },
      { item_id: '2', title: '身份认证', status: 'verified' },
    ])
    expect(actions).toHaveLength(1)
    expect(actions[0]).toMatchObject({
      id: '1',
      title: '补充学历',
      description: '上传证书',
      type: 'verification',
    })
  })
})
