import React, { useState, useEffect, useCallback } from 'react'
import { Box, Text, useInput } from 'ink'
import { theme } from '../lib/theme.js'
import type { HistoryEntry } from '../lib/ipcTypes.js'

interface Props {
  sessions: HistoryEntry[]
  onResume: (sessionId: string) => void
  onClose: () => void
}

/**
 * /history browser (§6.3): up/down arrows move through sessions, Enter
 * resumes the selected session. Esc/Backspace closes.
 */
export function HistoryScreen({ sessions, onResume, onClose }: Props) {
  const [selected, setSelected] = useState(0)

  useEffect(() => {
    setSelected(0)
  }, [sessions])

  const move = useCallback(
    (delta: number) => {
      setSelected(prev => {
        const next = prev + delta
        if (next < 0) return 0
        if (next >= sessions.length) return sessions.length - 1
        return next
      })
    },
    [sessions.length]
  )

  useInput((input, key) => {
    if (key.upArrow) move(-1)
    else if (key.downArrow) move(1)
    else if (key.return) {
      const s = sessions[selected]
      if (s) onResume(s.id)
    } else if (key.escape || input === 'q') {
      onClose()
    }
  })

  if (sessions.length === 0) {
    return (
      <Box flexDirection="column" borderStyle="round" borderColor={theme.border} padding={1}>
        <Text color={theme.text}>No past sessions yet.</Text>
        <Text dimColor>Press Esc to close.</Text>
      </Box>
    )
  }

  return (
    <Box flexDirection="column" borderStyle="round" borderColor={theme.border} padding={1}>
      <Text color={theme.primary} bold>
        ── Session History ── ({sessions.length})
      </Text>
      <Text dimColor>↑/↓ navigate · Enter resume · Esc close</Text>
      <Box flexDirection="column" marginTop={1}>
        {sessions.map((s, i) => {
          const selectedRow = i === selected
          const date = new Date(s.last_active_at)
          const when = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) +
            ' ' + date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
          return (
            <Box key={s.id} flexDirection="row">
              <Text color={selectedRow ? theme.primary : theme.muted} bold={selectedRow}>
                {selectedRow ? '▶ ' : '  '}
                {when}  {s.message_count} msgs  {s.active_model || 'no-model'}
              </Text>
              <Text color={theme.muted}></Text>
              <Text color={selectedRow ? theme.text : theme.muted}>
                {'  '}
                {s.preview.slice(0, 50)}
                {s.project_path ? `  [${s.project_path}]` : ''}
              </Text>
            </Box>
          )
        })}
      </Box>
    </Box>
  )
}