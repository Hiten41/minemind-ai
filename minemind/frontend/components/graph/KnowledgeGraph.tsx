'use client'

import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Edge,
  type Node
} from 'reactflow'
import 'reactflow/dist/style.css'

type KnowledgeGraphProps = {
  nodes: Node[]
  edges: Edge[]
  onNodeClick: (node: Node) => void
}

export default function KnowledgeGraph({ nodes, edges, onNodeClick }: KnowledgeGraphProps) {
  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      fitView
      onNodeClick={(_, node) => onNodeClick(node)}
    >
      <Background color="#333333" gap={18} />
      <Controls />
      <MiniMap nodeColor="#f59e0b" maskColor="rgba(0,0,0,0.7)" />
    </ReactFlow>
  )
}
