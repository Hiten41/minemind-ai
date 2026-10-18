import { afterEach, describe, expect, it, vi } from 'vitest'
import { forgetDataset, queryAI, uploadDocument } from '@/lib/api'

afterEach(() => vi.unstubAllGlobals())
describe('request contracts', () => {
  it('sends explicit all and selected scopes', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await queryAI('Compare documents', [], [])
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({ scope_mode: 'all', document_ids: [] })
    fetchMock.mockResolvedValue(new Response('{}', { status: 200 }))
    await queryAI('Pump pressure', [], ['document-two'])
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toMatchObject({ scope_mode: 'selected', document_ids: ['document-two'] })
  })
  it('does not report provider deletion failure as success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'delete_failed', detail: 'Retry deletion' }), { status: 503 })))
    await expect(forgetDataset('owned-dataset')).rejects.toThrow('Retry deletion')
  })
  it('preserves pending deletion for callers', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'delete_pending' }), { status: 202 })))
    expect(await forgetDataset('owned-dataset')).toEqual({ status: 'delete_pending' })
  })
  it('sends a stable caller-supplied idempotency key', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await uploadDocument(new File(['pump'], 'manual.txt'), 'manual', 'retry-key')
    expect(fetchMock.mock.calls[0][1].headers['Idempotency-Key']).toBe('retry-key')
  })
})
