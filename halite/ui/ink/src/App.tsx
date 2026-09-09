import React, { useEffect, useState, useCallback, useRef } from 'react'
import { Box, Static } from 'ink'
import { ChatDisplay, type ChatLineWithMeta } from './components/ChatDisplay.js'
import { InputBar } from './components/InputBar.js'
import { StatusBar } from './components/StatusBar.js'
import { Banner } from './components/Banner.js'
import { ConfirmPrompt } from './components/ConfirmPrompt.js'
import { BackendClient } from './backendClient.js'
import type { PythonToInk, ConfirmPayload } from './lib/ipcTypes.js'

type Props = {
  backend: BackendClient
}

interface ActiveConfirm {
  id: string
  kind: string
  payload: ConfirmPayload
}

// ── RENDERING MODEL ────────────────────────────────────────────────
// The terminal screen is split into two regions:
//
//  1. STATIC (scrollback) — written once, never redrawn:
//       ONE <Static> block holds the Banner (first item) and every
//       committed chat line (one item per line). Ink writes each item
//       to the terminal exactly once and NEVER re-diffs/redraws it;
//       subsequent frames only append NEW static items. This fixes the
//       stacked-duplicate-banner and interleaved-text corruption: those
//       items were plain dynamic children, so Ink re-rendered them on
//       every state change and the redraw math drifted.
//
//  2. LIVE (re-rendered each frame) — ONE contiguous bottom block:
//       thinking indicator, ConfirmPrompt, StatusBar, InputBar.
//       Ink's cursor-based redraw (log-update) only touches this block.
//       It sits entirely below the static scrollback, so the cursor
//       math cannot drift onto the banner/chat rows.

// Startup burst coalescing: the backend emits welcome, ready, and
// status_update in rapid succession at boot. Without batching, each one
// triggers a separate Ink frame, and the frame-height changes as the
// status bar fills in — which makes Ink's diff append rows instead of
// replacing them, stacking the banner/status 2-3 times. Coalescing the
// burst into a single frame keeps the first rendered frame stable.
const BURST_MS = 60

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
  const [activeConfirm, setActiveConfirm] = useState<ActiveConfirm | null>(null)

  // Coalescing timer for startup bursts
  const burstTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pending = useRef<PythonToInk[]>([])

  const flush = useCallback(() => {
    if (burstTimer.current) {
      clearTimeout(burstTimer.current)
      burstTimer.current = null
    }
    const batch = pending.current
    pending.current = []
    if (batch.length === 0) return
    // Apply the whole batch synchronously — one render, one frame
    const nextLines = batch
      .filter(m => ['welcome', 'user_message', 'assistant_message', 'system_message', 'error_message', 'tool_result'].includes(m.type))
      .map(m => {
        const anyMsg = m as any
        if (m.type === 'welcome' || m.type === 'system_message') return { role: 'system' as const, text: anyMsg.message ?? anyMsg.text ?? '', ts: Date.now() }
        if (m.type === 'user_message') return { role: 'user' as const, text: m.text, ts: Date.now() }
        if (m.type === 'assistant_message') return { role: 'assistant' as const, text: m.text, model: anyMsg.model, ts: Date.now() }
        if (m.type === 'error_message') return { role: 'error' as const, text: m.text, ts: Date.now() }
        return { role: 'tool' as const, text: anyMsg.output ?? '', tool: anyMsg.tool, success: anyMsg.success, ts: Date.now() }
      })
    setLines(prev => [...prev, ...nextLines])

    for (const msg of batch) {
      switch (msg.type) {
        case 'thinking_start':
          setThinking({ active: true, label: (msg as any).label, start: Date.now() })
          setInputDisabled(true)
          break
        case 'thinking_stop':
          setThinking({ active: false, label: '' })
          setInputDisabled(false)
          break
        case 'thinking_label':
          setThinking(prev => ({ ...prev, label: (msg as any).label }))
          break
        case 'status_update':
          if (msg.model) setModel(msg.model)
          if (msg.backend) setBackendName(msg.backend)
          if (msg.session_id) setSessionId(msg.session_id)
          if (msg.cwd) setCwd(msg.cwd)
          break
        case 'ready':
          setInputDisabled(false)
          break
        case 'quit':
          process.exit(0)
      }
    }
  }, [])

  const enqueue = useCallback((msg: PythonToInk) => {
    pending.current.push(msg)
    if (burstTimer.current) {
      clearTimeout(burstTimer.current)
    }
    burstTimer.current = setTimeout(flush, BURST_MS)
  }, [flush])

  // Subscribe to backend messages
  useEffect(() => {
    const onMessage = (msg: PythonToInk) => {
      // Confirm requests are urgent — handle immediately, not coalesced.
      if (msg.type === 'confirm_request') {
        if (burstTimer.current) {
          clearTimeout(burstTimer.current)
          flush()
        }
        setActiveConfirm({
          id: msg.id,
          kind: msg.kind,
          payload: msg.payload,
        })
        setInputDisabled(true)
        return
      }
      enqueue(msg)
    }

    backend.on('message', onMessage)
    return () => {
      backend.removeListener('message', onMessage)
      if (burstTimer.current) clearTimeout(burstTimer.current)
    }
  }, [backend, enqueue, flush])

  // Flush any pending burst on unmount (safety)
  useEffect(() => {
    return () => {
      if (burstTimer.current) clearTimeout(burstTimer.current)
    }
  }, [])

  const handleSubmit = useCallback((text: string) => {
    backend.send({ type: 'user_input', text })
  }, [backend])

  const handleConfirmResponse = useCallback((id: string, approved: boolean) => {
    backend.send({ type: 'confirm_response', id, approved })
    setActiveConfirm(null)
    setInputDisabled(false)
  }, [backend])

  // Graceful quit: tell the backend to shut down, then exit once it's done
  const handleQuit = useCallback(() => {
    backend.stop()
    setTimeout(() => process.exit(0), 2000)
  }, [backend])

  return (
    <Box flexDirection="column">
      {/*
        ── STATIC SCROLLBACK ──────────────────────────────────────
        ONE <Static> block renders the banner + every committed chat
        line permanently above the live region. Ink's Static uses
        position:absolute and writes each item to the terminal exactly
        once — new items append below old ones, old items are NEVER
        re-diffed or redrawn. So the banner (first item) renders once
        no matter how many messages/confirms follow, and every
        committed line renders exactly once.
      */}
      <Static items={[0, ...lines.map((_, i) => i + 1)]}>
        {(item: number) => {
          if (item === 0) {
            return (
              <Box key={`banner-${item}`} flexDirection="column">
                <Banner />
              </Box>
            )
          }
          const line = lines[item - 1]
          return (
            <ChatDisplay
              key={`line-${item}`}
              lines={[line]}
              thinkingActive={false}
              thinkingLabel=""
              thinkingStart={undefined}
            />
          )
        }}
      </Static>

      {/*
        ── LIVE REGION (re-rendered each frame) ──────────────────
        ONE contiguous bottom block: thinking indicator, confirm
        prompt, status bar, input bar. All live content lives here and
        nowhere else — Ink's cursor-based redraw (log-update) only
        touches this block, which sits below the static scrollback, so
        the cursor math can't drift onto the banner/chat rows.
      */}
      <Box flexDirection="column">
        {thinking.active && thinking.start && (
          <ChatDisplay
            lines={[]}
            thinkingActive={thinking.active}
            thinkingLabel={thinking.label}
            thinkingStart={thinking.start}
          />
        )}

        {/* Confirmation prompt — shown inline when Python asks for user approval */}
        {activeConfirm && (
          <ConfirmPrompt
            id={activeConfirm.id}
            kind={activeConfirm.kind}
            payload={activeConfirm.payload}
            onRespond={handleConfirmResponse}
          />
        )}

        {/* Status bar — model │ backend │ cwd │ session */}
        <Box marginTop={1}>
          <StatusBar model={model} backend={backendName} cwd={cwd} sessionId={sessionId} />
        </Box>

        {/* Input bar */}
        <Box>
          <InputBar onSubmit={handleSubmit} disabled={inputDisabled || activeConfirm !== null} onQuit={handleQuit} />
        </Box>
      </Box>
    </Box>
  )
}