'use client'

import MessageBubble from '@/components/chat/MessageBubble'
import type { ChatMessage } from '@/types'

export default function ChatWindow({ messages }: { messages: ChatMessage[] }) {
  return (
    <div className="space-y-5">
      {messages.map((message, index) => (
        <MessageBubble key={`${message.role}-${index}`} message={message} />
      ))}
    </div>
  )
}
