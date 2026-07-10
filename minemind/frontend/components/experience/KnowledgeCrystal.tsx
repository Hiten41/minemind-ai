'use client'

import { Float, Line, PerspectiveCamera, Sparkles } from '@react-three/drei'
import { Canvas, useFrame } from '@react-three/fiber'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Group, Mesh } from 'three'
import * as THREE from 'three'

type NodePoint = {
  position: [number, number, number]
  size: number
}

type KnowledgeCrystalProps = {
  queryPulse?: number
  optimizePulse?: number
  onReady?: () => void
}

function MemoryNode({
  node,
  index,
  active,
  optimizing
}: {
  node: NodePoint
  index: number
  active: boolean
  optimizing: boolean
}) {
  const meshRef = useRef<Mesh>(null)
  const base = useMemo(() => new THREE.Vector3(...node.position), [node.position])
  const cluster = useMemo(() => base.clone().multiplyScalar(0.22), [base])
  const normalColor = index % 3 === 0 ? '#e9d7b3' : '#a7adb2'
  const activeColor = index % 2 === 0 ? '#9ee7ff' : '#f1d18d'

  useFrame(({ clock }) => {
    if (!meshRef.current) return

    const target = optimizing ? cluster : base
    meshRef.current.position.lerp(target, 0.085)

    const pulse = active ? 1 + Math.sin(clock.elapsedTime * 7.5 + index) * 0.34 : 1
    const optimizePulse = optimizing ? 1.25 + Math.sin(clock.elapsedTime * 15 + index) * 0.2 : 1
    const scale = node.size * pulse * optimizePulse
    meshRef.current.scale.setScalar(scale / node.size)
  })

  return (
    <mesh ref={meshRef} position={node.position}>
      <sphereGeometry args={[node.size, 22, 22]} />
      <meshBasicMaterial
        color={active || optimizing ? activeColor : normalColor}
        toneMapped={false}
        transparent
        opacity={active || optimizing ? 1 : 0.78}
      />
    </mesh>
  )
}

function MemoryCore({
  queryPulse = 0,
  optimizePulse = 0,
  mobile = false
}: KnowledgeCrystalProps & { mobile?: boolean }) {
  const groupRef = useRef<Group>(null)
  const [activeNodes, setActiveNodes] = useState<number[]>([])
  const [optimizing, setOptimizing] = useState(false)
  const nodes = useMemo<NodePoint[]>(() => {
    const count = mobile ? 12 : 18
    return Array.from({ length: count }, (_, index) => {
      const angle = index * 2.399963
      const y = 1 - (index / (count - 1)) * 2
      const radius = Math.sqrt(1 - y * y) * 1.75
      return {
        position: [
          Math.cos(angle) * radius,
          y * 1.28,
          Math.sin(angle) * radius
        ],
        size: index % 4 === 0 ? 0.06 : 0.042
      }
    })
  }, [])

  const links = useMemo(() => {
    const pairs: Array<[NodePoint, NodePoint]> = []
    nodes.forEach((node, index) => {
      pairs.push([node, nodes[(index + 5) % nodes.length]])
      pairs.push([node, nodes[(index + 1) % nodes.length]])
    })
    return pairs
  }, [nodes])

  useFrame((_, delta) => {
    if (!groupRef.current) return
    groupRef.current.rotation.y += delta * 0.18
    groupRef.current.rotation.x = Math.sin(Date.now() * 0.00035) * 0.08
    const targetScale = optimizing ? 0.58 : 1
    groupRef.current.scale.lerp(new THREE.Vector3(targetScale, targetScale, targetScale), 0.08)
  })

  useEffect(() => {
    if (queryPulse === 0) return
    const selected = new Set<number>()
    while (selected.size < 7) {
      selected.add(Math.floor(Math.random() * nodes.length))
    }
    setActiveNodes(Array.from(selected))
    const timeout = window.setTimeout(() => setActiveNodes([]), 3200)
    return () => window.clearTimeout(timeout)
  }, [nodes.length, queryPulse])

  useEffect(() => {
    if (optimizePulse === 0) return
    setOptimizing(true)
    setActiveNodes(nodes.map((_, index) => index))
    const collapse = window.setTimeout(() => setOptimizing(false), 1350)
    const clear = window.setTimeout(() => setActiveNodes([]), 2550)
    return () => {
      window.clearTimeout(collapse)
      window.clearTimeout(clear)
    }
  }, [nodes, optimizePulse])

  return (
    <group ref={groupRef}>
      <Float speed={1.2} rotationIntensity={0.2} floatIntensity={0.5}>
        <mesh>
          <icosahedronGeometry args={[1.25, mobile ? 1 : 2]} />
          <meshPhysicalMaterial
            color={optimizing ? '#f4d28e' : '#d7c59d'}
            roughness={0.18}
            metalness={0.25}
            transmission={0.42}
            thickness={0.9}
            transparent
            opacity={optimizing ? 0.62 : 0.38}
            clearcoat={1}
            clearcoatRoughness={0.08}
            emissive={optimizing ? '#f4d28e' : '#6b5734'}
            emissiveIntensity={optimizing ? 0.58 : 0.16}
          />
        </mesh>
        <mesh scale={1.08}>
          <icosahedronGeometry args={[1.25, 1]} />
          <meshBasicMaterial color="#f0d7a3" wireframe transparent opacity={0.12} />
        </mesh>
      </Float>

      {links.map(([start, end], index) => (
        <Line
          key={`${index}-${start.position.join(',')}`}
          points={[start.position, end.position]}
          color="#d7b779"
          transparent
          opacity={activeNodes.length > 0 ? 0.34 : 0.18}
          lineWidth={0.7}
        />
      ))}

      {nodes.map((node, index) => (
        <MemoryNode
          key={index}
          node={node}
          index={index}
          active={activeNodes.includes(index)}
          optimizing={optimizing}
        />
      ))}

      <Sparkles
        count={mobile ? (optimizing ? 54 : 32) : (optimizing ? 120 : 75)}
        scale={[5.2, 3.4, 5.2]}
        size={optimizing ? 1.9 : 1.2}
        speed={optimizing ? 0.72 : 0.22}
        color={activeNodes.length > 0 ? '#9ee7ff' : '#d7b779'}
        opacity={activeNodes.length > 0 ? 0.58 : 0.34}
      />
    </group>
  )
}

export default function KnowledgeCrystal({ queryPulse = 0, optimizePulse = 0, onReady }: KnowledgeCrystalProps) {
  const [isMobile, setIsMobile] = useState(false)
  const [contextLost, setContextLost] = useState(false)

  useEffect(() => {
    const media = window.matchMedia('(max-width: 640px), (pointer: coarse)')
    const sync = () => setIsMobile(media.matches)
    sync()
    media.addEventListener('change', sync)
    return () => media.removeEventListener('change', sync)
  }, [])

  if (contextLost) {
    return (
      <div className="pointer-events-none grid h-full w-full place-items-center">
        <div className="relative h-[min(78vw,320px)] w-[min(78vw,320px)] rounded-full border border-[#d7b779]/15 bg-[radial-gradient(circle_at_45%_38%,rgba(215,183,121,0.22),rgba(255,255,255,0.035)_46%,transparent_72%)] shadow-[inset_0_0_90px_rgba(215,183,121,0.1),0_0_90px_rgba(215,183,121,0.08)]">
          <div className="absolute inset-[18%] rounded-full border border-white/[0.08]" />
          <div className="absolute inset-[31%] rounded-full border border-[#d7b779]/[0.16]" />
          <span className="absolute left-[28%] top-[34%] h-2.5 w-2.5 rounded-full bg-[#f1d18d]" />
          <span className="absolute right-[30%] top-[42%] h-2 w-2 rounded-full bg-white/70" />
          <span className="absolute bottom-[30%] left-[42%] h-3 w-3 rounded-full bg-[#f1d18d]/80" />
        </div>
      </div>
    )
  }

  return (
    <Canvas
      dpr={isMobile ? [1, 1.15] : [1, 1.5]}
      gl={{
        alpha: true,
        antialias: !isMobile,
        failIfMajorPerformanceCaveat: false,
        powerPreference: isMobile ? 'low-power' : 'high-performance',
        stencil: false
      }}
      className="h-full w-full pointer-events-none"
      style={{ pointerEvents: 'none' }}
      onCreated={({ gl }) => {
        gl.domElement.addEventListener('webglcontextlost', (event) => {
          event.preventDefault()
          setContextLost(true)
        })
        onReady?.()
      }}
    >
      <PerspectiveCamera makeDefault position={[0, 0.1, 6.1]} fov={38} />
      <ambientLight intensity={0.22} />
      <pointLight position={[3.4, 3.1, 4.5]} intensity={1.5} color="#d7b779" />
      <pointLight position={[-4, -1.6, -2]} intensity={1.1} color="#5e6874" />
      <spotLight position={[0, 5, 2]} angle={0.38} penumbra={0.7} intensity={1.2} color="#ffffff" />
      <fog attach="fog" args={['#000000', 5.8, 10]} />
      <MemoryCore queryPulse={queryPulse} optimizePulse={optimizePulse} mobile={isMobile} />
    </Canvas>
  )
}
