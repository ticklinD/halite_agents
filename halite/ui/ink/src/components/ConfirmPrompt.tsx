import React, { useState, useCallback } from 'react'
import { Box, Text, useInput } from 'ink'
import { theme } from '../lib/theme.js'
import type {
  ConfirmPayload,
  ConfirmDiffPayload,
  ConfirmDangerousPayload,
  ConfirmApiPayload,
  ConfirmCustomPayload,
} from '../lib/ipcTypes.js'

interface ConfirmPromptProps {
  id: string
  kind: string
  payload: ConfirmPayload
  onRespond: (id: string, approved: boolean) => void
}

function DiffPrompt({ payload }: { payload: ConfirmDiffPayload }) {
  return (
    <Box flexDirection="column">
      <Text color={theme.accent} bold>⚡ Confirm file overwrite</Text>
      <Box marginTop={1}>
        <Text color={theme.text}>  Path: </Text>
        <Text color={theme.primary}>{payload.path}</Text>
      </Box>
      {payload.old_preview && (
        <Box marginTop={1} flexDirection="column">
          <Text color={theme.muted}>  Current content (preview):</Text>
          <Text color={theme.muted}>  ────────────────────────</Text>
          {payload.old_preview.split('\n').slice(0, 6).map((line, i) => (
            <Text key={i} color={theme.muted}>  {line}</Text>
          ))}
          <Text color={theme.muted}>  ────────────────────────</Text>
        </Box>
      )}
      {payload.new_preview && (
        <Box marginTop={1} flexDirection="column">
          <Text color={theme.muted}>  New content (preview):</Text>
          <Text color={theme.muted}>  ────────────────────────</Text>
          {payload.new_preview.split('\n').slice(0, 6).map((line, i) => (
            <Text key={i} color={theme.text}>  {line}</Text>
          ))}
          <Text color={theme.muted}>  ────────────────────────</Text>
        </Box>
      )}
    </Box>
  )
}

function DangerousPrompt({ payload }: { payload: ConfirmDangerousPayload }) {
  return (
    <Box flexDirection="column">
      <Text color="#FF4444" bold>⛔ Dangerous command detected</Text>
      <Box marginTop={1}>
        <Text color={theme.text}>  Command: </Text>
        <Text color={theme.accent} bold>{payload.command}</Text>
      </Box>
      <Box>
        <Text color={theme.muted}>  Reason:  {payload.reason}</Text>
      </Box>
    </Box>
  )
}

function ApiPrompt({ payload }: { payload: ConfirmApiPayload }) {
  return (
    <Box flexDirection="column">
      <Text color={theme.accent} bold>💳 Route to paid API?</Text>
      <Box marginTop={1}>
        <Text color={theme.text}>  Task: {payload.task_description}</Text>
      </Box>
      <Box>
        <Text color={theme.muted}>  Reason: {payload.reasoning}</Text>
      </Box>
      {payload.estimated_tokens !== undefined && (
        <Box>
          <Text color={theme.muted}>  Est. tokens: ~{payload.estimated_tokens.toLocaleString()}</Text>
        </Box>
      )}
    </Box>
  )
}

function CustomPrompt({ payload }: { payload: ConfirmCustomPayload }) {
  return (
    <Box flexDirection="column">
      <Text color={theme.accent} bold>❓ Confirmation needed</Text>
      <Box marginTop={1}>
        <Text color={theme.text}>  {payload.message}</Text>
      </Box>
    </Box>
  )
}

export function ConfirmPrompt({ id, kind, payload, onRespond }: ConfirmPromptProps) {
  // [y] Approve  /  [n] Decline  — via Ink's useInput hook.
  // Ink owns stdin (raw mode + parsing) and routes every keypress to all
  // mounted useInput handlers. The InputBar is disabled while a confirm is
  // active, so it ignores keys; we act on them here. No manual
  // process.stdin.setRawMode toggling — that was fighting Ink's stdin
  // ownership and could leave the terminal in a broken raw state.
  const [answered, setAnswered] = useState(false)
  const [result, setResult] = useState<'approved' | 'denied' | null>(null)

  const respond = useCallback((approved: boolean) => {
    if (answered) return
    setAnswered(true)
    setResult(approved ? 'approved' : 'denied')
    onRespond(id, approved)
  }, [answered, id, onRespond])

  useInput((input, key) => {
    // 'y' / Enter = approve; 'n' / Escape / Ctrl+C = decline
    if (input === 'y' || input === 'Y' || key.return) {
      respond(true)
    } else if (input === 'n' || input === 'N' || key.escape || (key.ctrl && input === 'c')) {
      respond(false)
    }
  })

  if (answered) {
    return (
      <Box marginLeft={2}>
        <Text color={result === 'approved' ? theme.primary : '#FF6666'}>
          {result === 'approved' ? '✓ Approved' : '✗ Declined'}
        </Text>
      </Box>
    )
  }

  // Render the kind-specific detail block
  const DetailComponent = (() => {
    switch (kind) {
      case 'diff': return <DiffPrompt payload={payload as ConfirmDiffPayload} />
      case 'dangerous': return <DangerousPrompt payload={payload as ConfirmDangerousPayload} />
      case 'api': return <ApiPrompt payload={payload as ConfirmApiPayload} />
      default: return <CustomPrompt payload={payload as ConfirmCustomPayload} />
    }
  })()

  return (
    <Box flexDirection="column" marginLeft={2} borderStyle="round" borderColor={theme.border} paddingLeft={1} paddingRight={1}>
      {DetailComponent}
      <Box marginTop={1}>
        <Text color={theme.text}>  [</Text>
        <Text color={theme.primary} bold>y</Text>
        <Text color={theme.text}>] Approve  </Text>
        <Text color={theme.text}>[</Text>
        <Text color={theme.primary} bold>n</Text>
        <Text color={theme.text}>] Decline</Text>
      </Box>
    </Box>
  )
}