import React, { useEffect, useState } from 'react'
import { Text } from 'ink'

const BRAILLE = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

type Props = {
  label: string
}

export function ThinkingIndicator({ label }: Props) {
  const [frame, setFrame] = useState(0)
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const spinTimer = setInterval(() => {
      setFrame(f => (f + 1) % BRAILLE.length)
    }, 80)

    const elapsedTimer = setInterval(() => {
      setElapsed(e => e + 1)
    }, 1000)

    return () => {
      clearInterval(spinTimer)
      clearInterval(elapsedTimer)
    }
  }, [])

  const timeStr = elapsed < 10 ? `${(elapsed * 0.1).toFixed(1)}s` : `${elapsed}s`

  return (
    <Text>
      <Text color="cyan" bold> {BRAILLE[frame]} </Text>
      <Text color="yellow">{label}</Text>
      <Text color="gray"> ({timeStr})</Text>
    </Text>
  )
}
