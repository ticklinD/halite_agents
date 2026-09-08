/**
 * Backend IPC client — spawns the Python agent backend and manages
 * JSON-over-stdio communication. Node is the parent (owns the TTY),
 * Python is the child (pure logic, no terminal).
 */
import { spawn, type ChildProcess } from 'node:child_process'
import { EventEmitter } from 'node:events'
import { existsSync } from 'node:fs'
import { delimiter, resolve } from 'node:path'
import { createInterface } from 'node:readline'
import type { PythonToInk, InkToPython } from './lib/ipcTypes.js'

const resolvePython = (): string => {
  // Look for the project venv first
  const candidates = [
    process.env.HALITE_PYTHON,
    resolve(process.cwd(), '.venv/bin/python'),
    resolve(process.cwd(), '.venv/bin/python3'),
  ].filter(Boolean) as string[]

  for (const p of candidates) {
    if (existsSync(p)) return p
  }
  return 'python3'
}

export class BackendClient extends EventEmitter {
  private proc: ChildProcess | null = null
  private rl: ReturnType<typeof createInterface> | null = null
  private ready = false

  start(projectDir: string): void {
    const python = resolvePython()
    const args = ['-m', 'halite.backend']

    this.proc = spawn(python, args, {
      cwd: projectDir,
      env: {
        ...process.env,
        HALITE_ROOT: projectDir,
      },
      stdio: ['pipe', 'pipe', 'pipe'],
    })

    this.proc.on('error', err => {
      this.emit('error', `Failed to start backend: ${err.message}`)
    })

    this.proc.on('exit', code => {
      this.emit('exit', code)
    })

    // Read JSON events from backend stdout
    this.rl = createInterface({ input: this.proc.stdout! })
    this.rl.on('line', line => {
      const trimmed = line.trim()
      if (!trimmed) return
      try {
        const msg = JSON.parse(trimmed) as PythonToInk
        if (msg.type === 'ready') {
          this.ready = true
        }
        this.emit('message', msg)
      } catch {
        // Not JSON — log for debugging
        this.emit('stderr', trimmed)
      }
    })

    // Forward backend stderr for debugging
    this.proc.stderr?.on('data', (d: Buffer) => {
      this.emit('stderr', d.toString())
    })
  }

  send(msg: InkToPython): void {
    if (!this.proc?.stdin?.writable) return
    this.proc.stdin.write(JSON.stringify(msg) + '\n')
  }

  isReady(): boolean {
    return this.ready
  }

  stop(): void {
    this.send({ type: 'quit' })
    setTimeout(() => {
      if (this.proc && this.proc.exitCode === null) {
        this.proc.kill()
      }
    }, 1500)
  }
}