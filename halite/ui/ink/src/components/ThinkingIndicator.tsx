import React, { useEffect, useMemo, useState } from 'react'
import { Text } from 'ink'
import spinners from 'unicode-animations'

import { theme } from '../lib/theme.js'

const THINK: Array<keyof typeof spinners> = ['helix', 'breathe', 'orbit', 'dna', 'waverows', 'snake', 'pulse']
const TOOL: Array<keyof typeof spinners> = ['cascade', 'scan', 'diagswipe', 'fillsweep', 'rain', 'columns', 'sparkle']

const fmtElapsed = (ms: number) => {
  const sec = Math.max(0, ms) / 1000
  return sec < 10 ? `${sec.toFixed(1)}s` : `${Math.round(sec)}s`
}

const pick = <T,>(arr: T[]): T => arr[Math.floor(Math.random() * arr.length)]!

export function Spinner({ color, variant = 'think' }: { color: string; variant?: 'think' | 'tool' }) {
  const spin = useMemo(() => {
    const raw = spinners[pick(variant === 'tool' ? TOOL : THINK)]

    return { ...raw, frames: raw.frames.map(f => [...f][0] ?? '⠀') }
  }, [variant])

  const [frame, setFrame] = useState(0)

  useEffect(() => {
    setFrame(0)
  }, [spin])

  useEffect(() => {
    const id = setInterval(() => setFrame(f => (f + 1) % spin.frames.length), spin.interval)

    return () => clearInterval(id)
  }, [spin])

  return <Text color={color}>{spin.frames[frame]}</Text>
}

/** Live elapsed clock — `3.2s` ticking like Hermes' fmtDuration. */
export function ElapsedClock({ since }: { since: number }) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 100)

    return () => clearInterval(id)
  }, [since])

  return <Text color={theme.muted}>{fmtElapsed(now - since)}</Text>
}

/**
 * Thinking indicator: braille spinner + label + live elapsed clock,
 * styled like Hermes' FaceTicker (frame · duration).
 */
export function ThinkingIndicator({ label, color = theme.accent }: { label: string; color?: string }) {
  const [startedAt] = useState(() => Date.now())

  return (
    <Text>
      <Text color={color}>
        <Spinner color={color} variant="think" />
      </Text>
      <Text color={theme.muted}> {label}</Text>
      <Text color={theme.muted}> · </Text>
      <ElapsedClock since={startedAt} />
    </Text>
  )
}