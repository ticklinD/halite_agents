import React, { useEffect, useState, useCallback } from 'react'
import { Box, Text } from 'ink'
import { ChatDisplay, type ChatLineWithMeta } from './components/ChatDisplay.js'
import { InputBar } from './components/InputBar.js'
import { StatusBar } from './components/StatusBar.js'
import { Banner } from './components/Banner.js'
import { BackendClient } from './backendClient.js'
import type { PythonToInk } from './lib/ipcTypes.js'
import { theme } from './lib/theme.js'

type Props = {
  backend: BackendClient
}

export default function App({ backend }: Props) {
  const [lines, setLines] = useState<ChatLineWithMeta[]>([])
  const [thinking, setThinking] = useState<{
    active: boolean
    label: string
    start?: number
  }>({ active: false, label: '' })
  const [model, setModel] = useState('')
  const [backendName, setBackendName] = useState('')
  const [sessionId, setSessionId] = useState('')
  const [cwd, setCwd] = useState('')
  const [inputDisabled, setInputDisabled] = useState(false)

  // Subscribe to backend messages
  useEffect(() => {
    const onMessage = (msg: PythonToInk) => {
      switch (msg.type) {
        case 'ready':
          setInputDisabled(false)
          break
        case 'welcome':
          setLines(prev => [...prev, { role: 'system', text: msg.message, ts: Date.now() }])
          break
        case 'user_message':
          setLines(prev => [...prev, { role: 'user', text: msg.text, ts: Date.now() }])
          break
        case 'assistant_message':
          setLines(prev => [...prev, { role: 'assistant', text: msg.text, model: msg.model, ts: Date.now() }])
          break
        case 'system_message':
          setLines(prev => [...prev, { role: 'system', text: msg.text, ts: Date.now() }])
          break
        case 'error_message':
          setLines(prev => [...prev, { role: 'error', text: msg.text, ts: Date.now() }])
          break
        case 'thinking_start':
          setThinking({ active: true, label: msg.label, start: Date.now() })
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
          setLines(prev => [...prev, { role: 'tool', text: msg.output, tool: msg.tool, success: msg.success, ts: Date.now() }])
          break
        case 'status_update':
          if (msg.model) setModel(msg.model)
          if (msg.backend) setBackendName(msg.backend)
          if (msg.session_id) setSessionId(msg.session_id)
          if (msg.cwd) setCwd(msg.cwd)
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

  // Graceful quit: tell the backend to shut down, then exit once it's done
  const handleQuit = useCallback(() => {
    backend.stop()
    setTimeout(() => process.exit(0), 2000)
  }, [backend])

  return (
    <Box flexDirection="column" height="100%">
      {/* Banner — big block-letter HALITE art */}
      <Banner />

      {/* Chat area — takes remaining space, scrolls */}
      <Box flexDirection="column" flexGrow={1}>
        <ChatDisplay
          lines={lines}
          thinkingActive={thinking.active}
          thinkingLabel={thinking.label}
          thinkingStart={thinking.start}
        />
      </Box>

      {/* Input bar */}
      <Box>
        <InputBar onSubmit={handleSubmit} disabled={inputDisabled} onQuit={handleQuit} />
      </Box>

      {/* Status bar — model │ backend │ cwd │ session */}
      <Box marginTop={1}>
        <StatusBar model={model} backend={backendName} cwd={cwd} sessionId={sessionId} />
      </Box>
    </Box>
  )
}