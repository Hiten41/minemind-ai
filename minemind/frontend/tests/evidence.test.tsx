import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import EvidenceSource from '@/components/chat/EvidenceSource'
import { getDocumentFile } from '@/lib/api'
import type { Source } from '@/types'

vi.mock('@/lib/api', () => ({ getDocumentFile: vi.fn() }))
const source: Source = { title: 'same.pdf', document_id: 'owned-document-2', chunk_id: 'chunk', source_id: 'SRC_1', document_version: 'version', excerpt: 'No fire was reported.', relevance: 0, page: 2 }
beforeEach(() => {
  vi.mocked(getDocumentFile).mockReset()
  URL.createObjectURL = vi.fn(() => 'blob:source')
  URL.revokeObjectURL = vi.fn()
})
describe('source navigation', () => {
  it('opens the immutable document ID and correct PDF page', async () => {
    vi.mocked(getDocumentFile).mockResolvedValue(new Blob(['PDF'], { type: 'application/pdf' }))
    render(<EvidenceSource source={source} />)
    fireEvent.click(screen.getByRole('button'))
    await waitFor(() => expect(screen.getByTitle('Evidence from same.pdf')).toHaveAttribute('src', 'blob:source#page=2'))
    expect(getDocumentFile).toHaveBeenCalledWith('owned-document-2')
    expect(screen.getByText(source.excerpt)).toBeVisible()
  })
  it('retains historical passage but never fetches a deleted source', () => {
    render(<EvidenceSource source={{ ...source, available: false }} />)
    fireEvent.click(screen.getByRole('button'))
    expect(getDocumentFile).not.toHaveBeenCalled()
    expect(screen.getByRole('status')).toHaveTextContent('unavailable')
  })
  it('offers DOCX download with exact passage instead of an iframe', async () => {
    vi.mocked(getDocumentFile).mockResolvedValue(new Blob(['DOCX']))
    render(<EvidenceSource source={{ ...source, title: 'table.docx', section: 'Table 1 row 1 column 2' }} />)
    fireEvent.click(screen.getByRole('button'))
    expect(await screen.findByRole('link', { name: 'Download original' })).toBeVisible()
    expect(document.querySelector('iframe')).toBeNull()
  })
})
