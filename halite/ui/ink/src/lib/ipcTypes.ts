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
  | { type: 'quit' }

// ── Ink → Python (user input) ──────────────────────────────────────
export type InkToPython =
  | { type: 'user_input'; text: string }
  | { type: 'resize'; cols: number; rows: number }
  | { type: 'ready' }
  | { type: 'quit' }
