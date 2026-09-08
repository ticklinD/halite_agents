import React from 'react'
import { Text, Box } from 'ink'

export type ChatLine = {
  role: 'user' | 'assistant' | 'system' | 'error' | 'tool'
  text: string
  model?: string
  tool?: string
  success?: boolean
}

type Props = {
  lines: ChatLine[]
}

export function ChatDisplay({ lines }: Props) {
  return (
    <Box flexDirection="column">
      {lines.map((line, i) => {
        switch (line.role) {
          case 'user':
            return (
              <Text key={i}>
                <Text color="cyan" bold>{'>'} </Text>
                <Text color="white">{line.text}</Text>
              </Text>
            )
          case 'assistant':
            return (
              <Text key={i} wrap="wrap">
                <Text color="green" bold>{'◆ '} </Text>
                <Text>{line.text}</Text>
              </Text>
            )
          case 'system':
            return (
              <Text key={i} dimColor italic>
                {'  '}{line.text}
              </Text>
            )
          case 'error':
            return (
              <Text key={i}>
                <Text color="red" bold>{'✕ '} </Text>
                <Text color="red">{line.text}</Text>
              </Text>
            )
          case 'tool':
            return (
              <Text key={i}>
                <Text color={line.success ? 'green' : 'red'} bold>
                  {'    └─ '}{line.tool}{' '}
                </Text>
                <Text color={line.success ? 'green' : 'red'}>
                  [{line.success ? 'OK' : 'FAIL'}]
                </Text>
                <Text color="gray"> {line.text?.slice(0, 200)}</Text>
              </Text>
            )
          default:
            return null
        }
      })}
    </Box>
  )
}
