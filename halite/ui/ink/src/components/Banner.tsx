import React, { useEffect, useState } from 'react'
import { Box, Text, useStdout } from 'ink'
import { artWidth, logo, LOGO_WIDTH, theme } from '../lib/theme.js'

const TAG_FULL = 'Hybrid local/cloud TUI coding agent'
const HIDE_BELOW = 34
const COMPACT_FROM = 58

function ArtLines({ lines }: { lines: [string, string][] }) {
  return (
    <Box flexDirection="column" height={lines.length} width={artWidth(lines)}>
      {lines.map(([c, text], i) => (
        <Text color={c} key={i} wrap="truncate-end">
          {text}
        </Text>
      ))}
    </Box>
  )
}

function CompactBanner({ cols, name }: { cols: number; name: string }) {
  const w = Math.max(28, cols - 4)
  const label = name
  const slack = Math.max(0, w - label.length - 2)
  const left = slack >> 1
  const rule = `${'─'.repeat(left)} ${label} ${'─'.repeat(slack - left)}`

  return (
    <Box flexDirection="column" height={3} marginBottom={1} width={w}>
      <Text color={theme.primary}>{rule}</Text>
      <Text color={theme.muted}>{'  '.repeat(0)}</Text>
      <Text color={theme.primary}>{'─'.repeat(w)}</Text>
    </Box>
  )
}

export function Banner({ maxWidth }: { maxWidth?: number }) {
  const { stdout } = useStdout()
  // If stdout has no real width (piped/PTY test harness), assume 80 — the
  // full banner fits and users in real terminals always have real columns.
  const term = stdout?.columns && stdout.columns > 0 ? stdout.columns : 80
  const cols = Math.max(1, Math.min(term, maxWidth ?? term))

  if (cols < HIDE_BELOW) {
    return null
  }

  const logoLines = logo()

  if (cols >= LOGO_WIDTH + 2) {
    return (
      <Box flexDirection="column" marginBottom={1}>
        <ArtLines lines={logoLines} />
        <Text color={theme.muted} wrap="truncate-end">
          {TAG_FULL}
        </Text>
      </Box>
    )
  }

  if (cols >= COMPACT_FROM) {
    return <CompactBanner cols={cols} name="HALITE" />
  }

  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text bold color={theme.primary} wrap="truncate-end">
        HALITE
      </Text>
      <Text color={theme.muted} wrap="truncate-end">
        {TAG_FULL}
      </Text>
    </Box>
  )
}