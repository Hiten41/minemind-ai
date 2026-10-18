'use client'
import { useEffect, type Dispatch, type MutableRefObject, type SetStateAction } from 'react'
import { getChatHistory } from '@/lib/api'
import type { ChatMessage } from '@/types'

export function useChatHistory(
  interacted: MutableRefObject<boolean>,
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>,
  setError: Dispatch<SetStateAction<string>>
) {
  useEffect(() => {
    let cancelled = false
    getChatHistory().then((history) => {
      if (!cancelled && !interacted.current) setMessages(history)
    }).catch(() => {
      if (!cancelled) setError('Previous conversation could not be loaded. Current messages are preserved; refresh to retry history.')
    })
    return () => { cancelled = true }
  }, [interacted, setMessages, setError])
}
