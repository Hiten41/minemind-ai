import type { Source } from '@/types'

function evidenceTitle(title: string, index: number) {
  const cleanTitle = title.trim()
  if (!cleanTitle || cleanTitle.toLowerCase() === 'graph') {
    return `Memory evidence ${index + 1}`
  }
  return cleanTitle
}

export default function SourcePanel({ sources }: { sources: Source[] }) {
  return (
    <aside className="glass-depth-subtle min-h-0 overflow-hidden rounded-[24px] p-4 sm:rounded-[32px] sm:p-5">
      <p className="tracked-label text-[10px] text-white/34">Evidence</p>
      <h2 className="mt-2 text-xl font-semibold text-white">Sources</h2>
      {sources.length === 0 ? (
        <div className="mt-6 rounded-[24px] border border-white/10 bg-white/[0.04] p-5">
          <p className="text-sm leading-6 text-white/42">Ask a question to see the manuals and reports it's pulled from.</p>
        </div>
      ) : (
        <div className="mt-5 max-h-[420px] space-y-4 overflow-auto pr-1 lg:max-h-[calc(100vh-190px)]">
          {sources.map((source, index) => (
            <div key={`${source.title}-${source.excerpt}`} className="rounded-[24px] border border-white/10 bg-black/22 p-4">
              <h3 className="break-words font-semibold text-white/82">{evidenceTitle(source.title, index)}</h3>
              <p className="mt-2 break-words text-sm leading-6 text-white/44">{source.excerpt}</p>
              <div className="mt-4">
                <div className="mb-2 flex items-center justify-between text-[10px] uppercase tracking-[0.16em] text-white/34">
                  <span>Match strength</span>
                  <span>{Math.round(Math.max(0, Math.min(1, source.relevance)) * 100)}%</span>
                </div>
                <div className="h-1.5 rounded-full bg-white/10">
                  <div
                    className="h-1.5 rounded-full bg-[#d7b779]"
                    style={{ width: `${Math.max(0, Math.min(100, source.relevance * 100))}%` }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </aside>
  )
}
