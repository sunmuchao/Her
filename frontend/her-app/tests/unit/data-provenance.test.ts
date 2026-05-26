import { describe, expect, it } from 'vitest'
import { resolveProvenance } from '@/lib/data-provenance'

describe('data-provenance', () => {
  it('returns mock_fallback when using mock', () => {
    expect(resolveProvenance(true, true, '/v1/test')).toEqual({
      source: 'mock_fallback',
      api: '/v1/test',
      source_mode: undefined,
    })
  })

  it('returns empty when not mock and no data', () => {
    expect(resolveProvenance(false, false, '/v1/test', 'ledger_primary')).toEqual({
      source: 'empty',
      api: '/v1/test',
      source_mode: 'ledger_primary',
    })
  })

  it('returns api when not mock and has data', () => {
    expect(resolveProvenance(false, true, '/v1/trust-hub')).toEqual({
      source: 'api',
      api: '/v1/trust-hub',
      source_mode: undefined,
    })
  })
})
