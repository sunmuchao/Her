import { describe, expect, it } from 'vitest'
import {
  formatCollectedPreferenceChips,
  formatExplainSourceMap,
  mapCollectedToPreferenceGrid,
} from '@/lib/api/endpoints/collected'

describe('collected helpers', () => {
  it('formats collected statements into preference chips', () => {
    const chips = formatCollectedPreferenceChips({
      target_age_min: 25,
      target_age_max: 32,
      target_cities: '上海',
      persona_summary_internal: 'ignored',
    })
    expect(chips).toContain('年龄 25-32')
    expect(chips.some((item) => item.includes('上海'))).toBe(true)
  })

  it('maps collected statements to profile preference grid', () => {
    const grid = mapCollectedToPreferenceGrid({
      target_age_min: 26,
      target_age_max: 34,
      target_cities: '杭州',
      target_education_min: '本科',
      target_height_min: 165,
      target_height_max: 180,
    })
    expect(grid.ageRange).toBe('26-34岁')
    expect(grid.location).toBe('杭州')
    expect(grid.education).toBe('本科')
    expect(grid.height).toContain('165')
  })

  it('formats recommendation explain source map', () => {
    const lines = formatExplainSourceMap({
      target_cities: 'explicit_statement',
      target_age_min: 'profile_form',
    })
    expect(lines.some((line) => line.includes('城市'))).toBe(true)
    expect(lines.some((line) => line.includes('你明确说过'))).toBe(true)
  })
})
