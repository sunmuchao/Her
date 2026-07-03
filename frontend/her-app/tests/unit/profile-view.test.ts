import { describe, expect, it } from 'vitest'
import { buildProfileView } from '@/lib/mappers/profile-view'

describe('buildProfileView', () => {
  it('falls back to collected preferred_traits when onboarding tags are empty', () => {
    const view = buildProfileView(
      {
        user: {
          display_name: '测试用户',
        },
        onboarding: {
          preference: {},
        },
      },
      {
        profile_facts: {},
      },
      {
        collected_statements: {
          preferred_traits: ['情绪稳定', '会沟通'],
        },
      },
      undefined,
    )

    expect(view.tags).toEqual(['情绪稳定', '会沟通'])
  })

  it('prefers explicit onboarding tags when present', () => {
    const view = buildProfileView(
      {
        user: {
          display_name: '测试用户',
        },
        onboarding: {
          preference: {
            tags: ['阅读', '旅行'],
          },
        },
      },
      {
        profile_facts: {
          preferred_traits: ['旧标签'],
        },
      },
      {
        collected_statements: {
          preferred_traits: ['画像标签'],
        },
      },
      undefined,
    )

    expect(view.tags).toEqual(['阅读', '旅行'])
  })

  it('returns empty tags instead of placeholder when user has no saved tags', () => {
    const view = buildProfileView(
      {
        user: {
          display_name: '测试用户',
        },
        onboarding: {
          preference: {},
        },
      },
      {
        profile_facts: {},
      },
      {
        collected_statements: {},
      },
      undefined,
    )

    expect(view.tags).toEqual([])
  })
})
