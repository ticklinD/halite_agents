#!/usr/bin/env node
import React from 'react'
import { render } from 'ink'
import App from './App.js'
import { BackendClient } from './backendClient.js'

// Resolve the Halite project root (where .venv and halite/ live)
const projectDir = process.env.HALITE_ROOT || process.cwd()

// Spawn the Python backend
const backend = new BackendClient()
backend.on('stderr', (line: string) => {
  // Forward backend debug output (non-JSON) — helpful for debugging
  process.stderr.write(`[backend] ${line}`)
})

backend.start(projectDir)

// Tell the backend the UI is up
backend.send({ type: 'ready' })

// Inline rendering — Ink does NOT use the alternate screen buffer,
// so the TUI stays inline with the terminal, no cropping.
render(React.createElement(App, { backend }))

// Quit when backend dies unexpectedly
backend.on('exit', code => {
  process.exit(code ?? 0)
})