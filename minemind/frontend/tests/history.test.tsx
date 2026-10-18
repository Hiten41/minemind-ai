import { act, renderHook, waitFor } from '@testing-library/react'
import { useRef, useState } from 'react'
import { expect, it, vi } from 'vitest'
import { useChatHistory } from '@/components/chat/useChatHistory'
import { getChatHistory } from '@/lib/api'
import type { ChatMessage } from '@/types'

vi.mock('@/lib/api', () => ({ getChatHistory: vi.fn() }))
it.each(['resolve', 'reject'])('preserves a new message after stale history %s', async (outcome) => {
  let resolveHistory: (messages: ChatMessage[]) => void = () => {}
  let rejectHistory: (error: Error) => void = () => {}
  vi.mocked(getChatHistory).mockReturnValue(new Promise((resolve, reject) => { resolveHistory = resolve; rejectHistory = reject }))
  const { result } = renderHook(() => {
    const interacted = useRef(false)
    const [messages, setMessages] = useState<ChatMessage[]>([])
    const [error, setError] = useState('')
    useChatHistory(interacted, setMessages, setError)
    return { messages, error, send: () => { interacted.current = true; setMessages([{ role: 'user', content: 'New question' }]) } }
  })
  act(() => result.current.send())
  await act(async () => {
    if (outcome === 'resolve') resolveHistory([{ role: 'user', content: 'Old question' }])
    else rejectHistory(new Error('History unavailable'))
  })
  await waitFor(() => expect(result.current.messages[0].content).toBe('New question'))
  if (outcome === 'reject') expect(result.current.error).toContain('preserved')
})
