'use client'

import { useCallback, useMemo, useState } from 'react'

export type DataProvenanceSource = 'api' | 'mock_fallback' | 'empty'

export type DataProvenance = {
  source: DataProvenanceSource
  api?: string
  source_mode?: string
}

export function resolveProvenance(
  usingMock: boolean,
  hasData: boolean,
  api?: string,
  sourceMode?: string,
): DataProvenance {
  if (usingMock) return { source: 'mock_fallback', api, source_mode: sourceMode }
  if (!hasData) return { source: 'empty', api, source_mode: sourceMode }
  return { source: 'api', api, source_mode: sourceMode }
}

export function logDataProvenance(page: string, provenance: DataProvenance) {
  if (process.env.NODE_ENV === 'development') {
    // eslint-disable-next-line no-console -- dev-only data provenance tracing (§13.2)
    console.debug(`[data-provenance] ${page}`, provenance)
  }
}

export function usePageDataSource(initial: DataProvenance = { source: 'empty' }) {
  const [provenance, setProvenance] = useState<DataProvenance>(initial)

  const usingMockData = provenance.source === 'mock_fallback'

  const applyProvenance = useCallback(
    (usingMock: boolean, hasData: boolean, api?: string, sourceMode?: string) => {
      const next = resolveProvenance(usingMock, hasData, api, sourceMode)
      setProvenance(next)
      return next
    },
    [],
  )

  return useMemo(
    () => ({
      provenance,
      usingMockData,
      setProvenance,
      applyProvenance,
    }),
    [applyProvenance, provenance, usingMockData],
  )
}
