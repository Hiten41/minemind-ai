import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MessageBubble from '@/components/chat/MessageBubble'
import { getDocumentFile } from '@/lib/api'
import type { Source } from '@/types'

vi.mock('@/lib/api', () => ({ getDocumentFile: vi.fn() }))
const source: Source = { title: 'manual.pdf', document_id: 'manual-id', chunk_id: 'first',
  source_id: 'SRC_4', document_version: 'version', excerpt: 'Test the brakes at slow speed.', relevance: 0, page: 2 }

beforeEach(() => {
  vi.mocked(getDocumentFile).mockReset().mockResolvedValue(new Blob(['PDF'], { type: 'application/pdf' }))
  URL.createObjectURL = vi.fn(() => 'blob:source')
  URL.revokeObjectURL = vi.fn()
})

describe('readable answer citations', () => {
  it('collapses a long page list into one document control until requested', () => {
    const sources = Array.from({ length: 17 }, (_, i) => ({ ...source, page: i + 1, chunk_id: `chunk-${i}`, source_id: `SRC_${i + 1}` }))
    render(<MessageBubble message={{ role: 'assistant', content: 'Chapter list.', sources }} />)
    const group = screen.getByRole('button', { name: 'View evidence · manual.pdf' })
    expect(group).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Inspect evidence')).not.toBeInTheDocument()
    fireEvent.click(group)
    expect(screen.getAllByText('Inspect evidence')).toHaveLength(17)
    fireEvent.click(screen.getByRole('button', { name: 'Hide evidence · manual.pdf' }))
    expect(screen.queryByText('Inspect evidence')).not.toBeInTheDocument()
  })
  it('links readable API content without exposing internal source labels', async () => {
    const second = { ...source, source_id: 'SRC_5', chunk_id: 'second', excerpt: 'The retaining tabs were worn.' }
    render(<MessageBubble message={{ role: 'assistant', content: 'The switch was faulty. (pg. 2)',
      content_parts: [{ text: 'The switch was faulty. ', source_ids: [] }, { text: '(pg. 2)', source_ids: ['SRC_4', 'SRC_5'] }],
      sources: [source, second] }} />)
    expect(screen.queryByText(/SRC_/)).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'View source: manual.pdf, page 2' })).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'View source: manual.pdf, page 2' }))
    expect(screen.getByText(second.excerpt)).toBeVisible()
    await waitFor(() => expect(screen.getAllByTitle('Evidence from manual.pdf')[0]).toHaveAttribute('src', 'blob:source#page=2'))
  })

  it('renders legacy reasoning citations as page references', () => {
    render(<MessageBubble message={{ role: 'assistant', content: 'The switch was faulty.',
      reasoning: 'Supported by [SRC_4]', sources: [source] }} />)
    fireEvent.click(screen.getByRole('button', { name: 'Show Reasoning' }))
    expect(screen.queryByText(/\[SRC_4\]/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'View source: manual.pdf, page 2' })).toBeVisible()
  })

  it('does not replace an updated answer with stale structured content', () => {
    render(<MessageBubble message={{ role: 'assistant', content: 'Current answer. (pg. 2)',
      content_parts: [{ text: 'Outdated answer.', source_ids: [] }], sources: [source] }} />)
    expect(screen.getByText('Current answer. (pg. 2)')).toBeVisible()
    expect(screen.queryByText('Outdated answer.')).not.toBeInTheDocument()
  })

  it('replaces internal labels with a page control that opens the correct evidence', async () => {
    render(<MessageBubble message={{ role: 'assistant', content: 'Test brakes slowly. [SRC_4]', sources: [source] }} />)
    expect(screen.queryByText(/\[SRC_4\]/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'View source: manual.pdf, page 2' }))
    expect(screen.getByText(source.excerpt)).toBeVisible()
    await waitFor(() => expect(screen.getByTitle('Evidence from manual.pdf')).toHaveAttribute('src', 'blob:source#page=2'))
    expect(getDocumentFile).toHaveBeenCalledWith('manual-id')
  })

  it('groups adjacent citations on the same page while retaining both passages', () => {
    const second = { ...source, chunk_id: 'second', source_id: 'SRC_8', excerpt: 'Leave room to steer.' }
    render(<MessageBubble message={{ role: 'assistant', content: 'Check braking and steering. [SRC_4] [SRC_8]', sources: [source, second] }} />)
    expect(screen.getAllByRole('button', { name: 'View source: manual.pdf, page 2' })).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'View source: manual.pdf, page 2' }))
    expect(screen.getByText(source.excerpt)).toBeVisible()
    expect(screen.getByText(second.excerpt)).toBeVisible()
  })

  it('distinguishes documents with the same page number', () => {
    const second = { ...source, title: 'audit.pdf', document_id: 'audit-id', chunk_id: 'audit', source_id: 'SRC_8' }
    render(<MessageBubble message={{ role: 'assistant', content: 'The documents differ. [SRC_4] [SRC_8]', sources: [source, second] }} />)
    expect(screen.getByRole('button', { name: 'View source: manual.pdf, page 2' })).toHaveTextContent('manual.pdf · pg. 2')
    expect(screen.getByRole('button', { name: 'View source: audit.pdf, page 2' })).toHaveTextContent('audit.pdf · pg. 2')
  })

  it('keeps missing and deleted sources honest without exposing internal labels', () => {
    render(<MessageBubble message={{ role: 'assistant', content: 'Historical answer. [SRC_4] [SRC_99]', sources: [{ ...source, available: false }] }} />)
    expect(screen.getByText('Source unavailable')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'View source: manual.pdf, page 2' }))
    expect(screen.getByText(source.excerpt)).toBeVisible()
    expect(getDocumentFile).not.toHaveBeenCalled()
  })

  it('preserves user-authored text and supports sources without page numbers', () => {
    const { rerender } = render(<MessageBubble message={{ role: 'user', content: 'Explain [SRC_4]' }} />)
    expect(screen.getByText('Explain [SRC_4]')).toBeVisible()
    rerender(<MessageBubble message={{ role: 'assistant', content: 'Test the brakes. [SRC_4]', sources: [{ ...source, page: null, section: 'Brake checks' }] }} />)
    expect(screen.getByRole('button', { name: 'View source: manual.pdf, Brake checks' })).toHaveTextContent('Brake checks')
  })

  it('does not remove ordinary answer text that resembles a source label', () => {
    render(<MessageBubble message={{ role: 'assistant', content: '[SRC_LABEL] is a field mentioned by this document.' }} />)
    expect(screen.getByText('[SRC_LABEL] is a field mentioned by this document.')).toBeVisible()
  })
})
