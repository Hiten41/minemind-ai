import type { Source } from '@/types'
import EvidenceSource from './EvidenceSource'

export default function SourcePanel({ sources }: { sources: Source[] }) {
  return <aside className="glass-depth-subtle min-h-0 overflow-hidden rounded-[24px] p-4">
    <h2 className="text-xl font-semibold text-white">Sources</h2>
    {sources.length === 0 ? <p className="mt-4 text-sm text-white/50">No supporting sources for this response.</p> :
      <div className="mt-4 max-h-[70vh] space-y-3 overflow-auto">
        {sources.map((source, index) => <EvidenceSource key={`${source.chunk_id}-${index}`} source={source} />)}
      </div>}
  </aside>
}
