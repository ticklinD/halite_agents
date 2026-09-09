/**
 * IPC protocol types for Python ↔ Ink communication.
 * Messages are JSON-encoded, one per line over stdin/stdout.
 */

// ── Python → Ink (display commands) ────────────────────────────────
export type PythonToInk =
  | { type: 'ready' }
  | { type: 'welcome'; message: string }
  | { type: 'user_message'; text: string }
  | { type: 'assistant_message'; text: string; model?: string }
  | { type: 'system_message'; text: string }
  | { type: 'error_message'; text: string }
  | { type: 'thinking_start'; label: string }
  | { type: 'thinking_stop' }
  | { type: 'thinking_label'; label: string }
  | { type: 'tool_result'; tool: string; output: string; success: boolean }
  | { type: 'status_update'; model?: string; backend?: string; cost?: string; session_id?: string; cwd?: string }
  | { type: 'command_response'; text: string; action?: string }
  | { type: 'confirm_request'; id: string; kind: string; payload: ConfirmPayload }
  | { type: 'quit' }

// ── Ink → Python (user input) ──────────────────────────────────────
export type InkToPython =
  | { type: 'user_input'; text: string }
  | { type: 'resize'; cols: number; rows: number }
  | { type: 'ready' }
  | { type: 'confirm_response'; id: string; approved: boolean }
  | { type: 'quit' }

// ── Confirm payloads by kind ────────────────────────────────────────
export type ConfirmPayload =
  | ConfirmDiffPayload
  | ConfirmDangerousPayload
  | ConfirmApiPayload
  | ConfirmCustomPayload

export interface ConfirmDiffPayload {
  path: string
  old_preview?: string
  new_preview?: string
}

export interface ConfirmDangerousPayload {
  command: string
  reason: string
}

export interface ConfirmApiPayload {
  task_description: string
  reasoning: string
  estimated_tokens?: number
}

export interface ConfirmCustomPayload {
  message: string
  options?: string[]
}
