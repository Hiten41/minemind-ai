export default function ReasoningPanel({ reasoning }: { reasoning: string }) {
  return (
    <div className="rounded-lg bg-background p-3 text-sm leading-6 text-[#d1d5db]">
      {reasoning}
    </div>
  )
}
