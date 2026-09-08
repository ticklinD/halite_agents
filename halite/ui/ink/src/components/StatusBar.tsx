import React from 'react'
import { Box, Text } from 'ink'

type Props = {
  model: string
  backend: string
  cost?: string
}

export function StatusBar({ model, backend, cost }: Props) {
  return (
    <Box justifyContent="space-between">
      <Text color="blue" bold>{'halite'}</Text>
      <Text color="gray">{model || 'none'} ({backend || 'unknown'})</Text>
      <Text color="gray">{cost || ''}</Text>
      <Text color="gray" dimColor>{'/help for commands'}</Text>
    </Box>
  )
}
