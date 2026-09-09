/**
 * IPC protocol types for Python ↔ Ink communication.
 * Messages are JSON-encoded, one per line over stdin/stdout.
 */

// ── Python → Ink (display commands) ────────────────────────────────
export interface HistoryEntry {
  id: string
  project_path: string | null
  active_model: string
  backend: string
  created_at: string
  last_active_at: string
  message_count: number
  preview: string
}

export interface ConfigField {
  key: string
  label: string
  value: string
  type: 'string' | 'number' | 'boolean' | 'select'
  options?: string[]
  help?: string
}

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
  | { type: 'command_action'; action: string; message?: string }
  | { type: 'confirm_request'; id: string; kind: string; payload: ConfirmPayload }
  | { type: 'history_data'; sessions: HistoryEntry[] }
  | { type: 'config_data'; fields: ConfigField[] }
  | { type: 'config_saved'; message: string }
  | { type: 'resume_ok'; session_id: string; messages: ChatHistoryMessage[] }
  | { type: 'quit' }

// A message in a resumed session (for /history resume → shows in chat)
export interface ChatHistoryMessage {
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  model_used?: string
  created_at?: string
}

// ── Ink → Python (user input) ──────────────────────────────────────
export type InkToPython =
  | { type: 'user_input'; text: string }
  | { type: 'resize'; cols: number; rows: number }
  | { type: 'ready' }
  | { type: 'confirm_response'; id: string; approved: boolean }
  | { type: 'resume_session'; session_id: string }
  | { type: 'config_update'; updates: Record<string, string | number | boolean> }
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
