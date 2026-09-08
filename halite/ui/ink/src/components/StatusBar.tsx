import React from 'react'
import { Box, Text } from 'ink'

import { theme } from '../lib/theme.js'

type Props = {
  model: string
  backend: string
  cwd?: string
  sessionId?: string
  version?: string
}

// Hermes-style status rule: `│`-separated segments in muted/bronze.
export function StatusBar({ model, backend, cwd, sessionId, version = 'v0.1.0' }: Props) {
  const segs: string[] = []

  if (version) segs.push(`Halite ${version}`)
  if (model) segs.push(model)
  if (backend) segs.push(backend)
  if (cwd) segs.push(cwd)
  if (sessionId) segs.push(`session ${sessionId.slice(0, 8)}`)

  return (
    <Box>
      <Text color={theme.muted} dimColor>
        {segs.join(' │ ')}
      </Text>
    </Box>
  )
}