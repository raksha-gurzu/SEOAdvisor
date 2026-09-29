import type {
  Defaults,
  GapDefaults,
  GapRecord,
  GapSettingsIn,
  GapSummary,
  Health,
  RunRecord,
  RunSettings,
  RunSummary,
  SnapshotDefaults,
  SnapshotRecord,
  SnapshotSettingsIn,
  SnapshotSummary,
} from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!resp.ok) {
    let message = `${resp.status} ${resp.statusText}`
    try {
      const body = await resp.json()
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join('; ')
    } catch {
      // keep the status text
    }
    throw new Error(message)
  }
  return resp.status === 204 ? (undefined as T) : resp.json()
}

export const api = {
  health: () => request<Health>('/health'),
  defaults: () => request<Defaults>('/settings/defaults'),
  listRuns: () => request<RunSummary[]>('/runs'),
  getRun: (id: string) => request<RunRecord>(`/runs/${id}`),
  startRun: (page_text: string, settings: RunSettings, source_url: string | null = null) =>
    request<{ id: string }>('/runs', { method: 'POST', body: JSON.stringify({ page_text, settings, source_url }) }),
  deleteRun: (id: string) => request<void>(`/runs/${id}`, { method: 'DELETE' }),
  gapDefaults: () => request<GapDefaults>('/gaps/defaults'),
  listGaps: () => request<GapSummary[]>('/gaps'),
  getGap: (id: string) => request<GapRecord>(`/gaps/${id}`),
  startGap: (site: string, competitors: string[], settings: GapSettingsIn) =>
    request<{ id: string }>('/gaps', { method: 'POST', body: JSON.stringify({ site, competitors, settings }) }),
  deleteGap: (id: string) => request<void>(`/gaps/${id}`, { method: 'DELETE' }),
  snapshotDefaults: () => request<SnapshotDefaults>('/snapshots/defaults'),
  listSnapshots: () => request<SnapshotSummary[]>('/snapshots'),
  getSnapshot: (id: string) => request<SnapshotRecord>(`/snapshots/${id}`),
  startSnapshot: (site: string, settings: SnapshotSettingsIn) =>
    request<{ id: string }>('/snapshots', { method: 'POST', body: JSON.stringify({ site, settings }) }),
  deleteSnapshot: (id: string) => request<void>(`/snapshots/${id}`, { method: 'DELETE' }),
  extract: (url: string) =>
    request<{ url: string; title: string; text: string; word_count: number; method: string }>('/extract', {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),
}
