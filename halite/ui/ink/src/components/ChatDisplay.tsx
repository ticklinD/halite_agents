import React from 'react'
import { Box, Text } from 'ink'

import { theme } from '../lib/theme.js'
import { ElapsedClock, Spinner } from './ThinkingIndicator.js'

export type ChatLine = {
  role: 'user' | 'assistant' | 'system' | 'error' | 'tool'
  text: string
  model?: string
  tool?: string
  success?: boolean
}

// ── Role glyphs (Hermes ROLE map) ───────────────────────────────────
const ROLE_GLYPH = {
  user: '❯',
  assistant: '◆',
  system: '·',
  tool: '⚡',
  error: '✕'
} as const

const ROLE_COLOR = {
  user: theme.label,
  assistant: theme.text,
  system: theme.muted,
  tool: theme.tool,
  error: theme.error
} as const

function fmtTimestamp(ts?: number): string | null {
  if (typeof ts !== 'number' || !Number.isFinite(ts) || ts <= 0) return null
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return null
  return `[${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}]`
}

export type ChatLineWithMeta = ChatLine & { ts?: number }

type Props = {
  lines: ChatLineWithMeta[]
  thinkingActive: boolean
  thinkingLabel?: string
  thinkingStart?: number
}

export function ChatDisplay({ lines, thinkingActive, thinkingLabel, thinkingStart }: Props) {
  return (
    <Box flexDirection="column">
      {lines.map((line, i) => {
        const stamp = fmtTimestamp(line.ts)
        const glyph = ROLE_GLYPH[line.role]
        const color = ROLE_COLOR[line.role]

        switch (line.role) {
          case 'user':
            return (
              <Box key={i} marginTop={i > 0 ? 1 : 0}>
                <Text color={theme.border} bold>
                  {glyph}{' '}
                </Text>
                <Text color={color} bold>
                  {stamp ? `${stamp} ` : ''}
                  {line.text}
                </Text>
              </Box>
            )
          case 'assistant': {
            const hasDetails = Boolean(line.model)
            return (
              <Box key={i} flexDirection="column">
                {hasDetails && (
                  <Box marginBottom={1}>
                    <Text color={theme.muted} dimColor>
                      {'  '}└─{' '}
                    </Text>
                    <Text color={theme.muted} dimColor>
                      Response
                    </Text>
                  </Box>
                )}
                <Box>
                  <Text color={theme.border} bold>
                    {glyph}{' '}
                  </Text>
                  <Text color={color} wrap="wrap">
                    {stamp ? `${stamp} ` : ''}
                    {line.text}
                  </Text>
                </Box>
              </Box>
            )
          }
          case 'system':
            return (
              <Text key={i} color={theme.muted} dimColor italic>
                {'  '}{stamp ? `${stamp} ` : ''}{line.text}
              </Text>
            )
          case 'error':
            return (
              <Text key={i}>
                <Text color={theme.error} bold>
                  {glyph}{' '}
                </Text>
                <Text color={theme.error}>{line.text}</Text>
              </Text>
            )
          case 'tool':
            return (
              <Box
                key={i}
                alignSelf="flex-start"
                borderColor={theme.border}
                borderStyle="round"
                marginLeft={3}
                paddingX={1}
              >
                <Text color={line.success ? theme.ok : theme.error}>
                  {glyph} {line.tool} [{line.success ? 'OK' : 'FAIL'}]
                </Text>
                <Text color={theme.muted}> {line.text?.slice(0, 200)}</Text>
              </Box>
            )
          default:
            return null
        }
      })}

      {/* Live thinking row at the tail while the model is working */}
      {thinkingActive && thinkingStart && (
        <Box marginTop={1}>
          <Text color={theme.muted} dimColor>
            {'  '}└─{' '}
          </Text>
          <Text color={theme.accent}>
            <Spinner color={theme.accent} variant="think" />
          </Text>
          <Text color={theme.muted}> {thinkingLabel ?? 'thinking'} · </Text>
          <ElapsedClock since={thinkingStart} />
        </Box>
      )}
    </Box>
  )
}