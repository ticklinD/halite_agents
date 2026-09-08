import React, { useEffect, useState, useCallback } from 'react'
import { Box, Text } from 'ink'
import { ChatDisplay, type ChatLine } from './components/ChatDisplay.js'
import { InputBar } from './components/InputBar.js'
import { StatusBar } from './components/StatusBar.js'
import { ThinkingIndicator } from './components/ThinkingIndicator.js'
import { BackendClient } from './backendClient.js'
import type { PythonToInk } from './lib/ipcTypes.js'

type Props = {
  backend: BackendClient
}

export default function App({ backend }: Props) {
  const [lines, setLines] = useState<ChatLine[]>([])
  const [thinking, setThinking] = useState<{ active: boolean; label: string }>({ active: false, label: '' })
  const [model, setModel] = useState('')
  const [backendName, setBackendName] = useState('')
  const [inputDisabled, setInputDisabled] = useState(false)

  // Subscribe to backend messages
  useEffect(() => {
    const onMessage = (msg: PythonToInk) => {
      switch (msg.type) {
        case 'ready':
          setInputDisabled(false)
          break
        case 'welcome':
          setLines(prev => [...prev, { role: 'system', text: msg.message }])
          break
        case 'user_message':
          setLines(prev => [...prev, { role: 'user', text: msg.text }])
          break
        case 'assistant_message':
          setLines(prev => [...prev, { role: 'assistant', text: msg.text, model: msg.model }])
          break
        case 'system_message':
          setLines(prev => [...prev, { role: 'system', text: msg.text }])
          break
        case 'error_message':
          setLines(prev => [...prev, { role: 'error', text: msg.text }])
          break
        case 'thinking_start':
          setThinking({ active: true, label: msg.label })
          setInputDisabled(true)
          break
        case 'thinking_stop':
          setThinking({ active: false, label: '' })
          setInputDisabled(false)
          break
        case 'thinking_label':
          setThinking(prev => ({ ...prev, label: msg.label }))
          break
        case 'tool_result':
          setLines(prev => [...prev, { role: 'tool', text: msg.output, tool: msg.tool, success: msg.success }])
          break
        case 'status_update':
          if (msg.model) setModel(msg.model)
          if (msg.backend) setBackendName(msg.backend)
          break
        case 'quit':
          process.exit(0)
      }
    }

    backend.on('message', onMessage)
    return () => {
      backend.removeListener('message', onMessage)
    }
  }, [backend])

  const handleSubmit = useCallback((text: string) => {
    backend.send({ type: 'user_input', text })
  }, [backend])

  // Allow Ctrl+C to quit
  useEffect(() => {
    const onKey = (data: Buffer) => {
      if (data.toString() === '\u0003') {
        // Ctrl+C
        process.exit(0)
      }
    }
    process.stdin.on('data', onKey)
    return () => { process.stdin.removeListener('data', onKey) }
  }, [])

  return (
    <Box flexDirection="column" height="100%">
      {/* Header */}
      <Box>
        <Text color="cyan" bold>Halite</Text>
        <Text color="gray"> — hybrid TUI coding agent</Text>
      </Box>

      {/* Chat area — takes remaining space, scrolls */}
      <Box flexDirection="column" flexGrow={1}>
        <ChatDisplay lines={lines} />
      </Box>

      {/* Thinking indicator — shows when model is working */}
      {thinking.active && (
        <Box>
          <ThinkingIndicator label={thinking.label} />
        </Box>
      )}

      {/* Input bar */}
      <Box>
        <InputBar onSubmit={handleSubmit} disabled={inputDisabled} />
      </Box>

      {/* Status bar */}
      <Box>
        <StatusBar model={model} backend={backendName} />
      </Box>
    </Box>
  )
}