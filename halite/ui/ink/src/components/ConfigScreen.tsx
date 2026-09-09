import React, { useState, useEffect, useCallback } from 'react'
import { Box, Text, useInput } from 'ink'
import { theme } from '../lib/theme.js'
import type { ConfigField } from '../lib/ipcTypes.js'

interface Props {
  fields: ConfigField[]
  onSave: (updates: Record<string, string | number | boolean>) => void
  onClose: () => void
}

/**
 * /config settings form (§7.1). ↑/↓ move between fields; Enter edits the
 * selected field (or toggles boolean); for select fields ←/→ cycles
 * options; `s` saves all changes to ~/.halite/config.toml; Esc closes.
 */
export function ConfigScreen({ fields, onSave, onClose }: Props) {
  const [selected, setSelected] = useState(0)
  const [editing, setEditing] = useState(false)
  const [values, setValues] = useState<Record<string, string>>({})

  // Init values from incoming fields
  useEffect(() => {
    const init: Record<string, string> = {}
    for (const f of fields) init[f.key] = f.value
    setValues(init)
  }, [fields])

  const move = useCallback(
    (delta: number) => {
      if (editing) return
      setSelected(prev => {
        const next = prev + delta
        if (next < 0) return 0
        if (next >= fields.length) return fields.length - 1
        return next
      })
    },
    [editing, fields.length]
  )

  const toggleBoolean = useCallback((key: string, cur: string) => {
    setValues(prev => ({ ...prev, [key]: cur === 'true' ? 'false' : 'true' }))
  }, [])

  const cycleSelect = useCallback(
    (key: string, cur: string, delta: number) => {
      const field = fields.find(f => f.key === key)
      if (!field?.options?.length) return
      const idx = field.options.indexOf(cur)
      const next = (idx + delta + field.options.length) % field.options.length
      setValues(prev => ({ ...prev, [key]: field.options![next] }))
    },
    [fields]
  )

  useInput((input, key) => {
    if (key.escape) {
      if (editing) setEditing(false)
      else onClose()
      return
    }
    if (editing) {
      const field = fields[selected]
      if (key.return) setEditing(false)
      else if (key.leftArrow && field.type === 'select') cycleSelect(field.key, values[field.key] ?? '', -1)
      else if (key.rightArrow && field.type === 'select') cycleSelect(field.key, values[field.key] ?? '', 1)
      else if (field.type === 'string' || field.type === 'number') {
        // Type into the string/number field
        setValues(prev => {
          const cur = prev[field.key] ?? ''
          if (key.backspace) return { ...prev, [field.key]: cur.slice(0, -1) }
          // Only printable single chars
          if (input && input.length === 1 && !key.ctrl) return { ...prev, [field.key]: cur + input }
          return prev
        })
      } else if (field.type === 'boolean') {
        toggleBoolean(field.key, values[field.key] ?? 'false')
      }
      return
    }
    if (key.upArrow) move(-1)
    else if (key.downArrow) move(1)
    else if (key.return) {
      const field = fields[selected]
      if (field.type === 'select') cycleSelect(field.key, values[field.key] ?? '', 1)
      else setEditing(true)
    } else if (input === 's' || input === 'S') {
      // Save: convert string values to proper types
      const updates: Record<string, string | number | boolean> = {}
      for (const f of fields) {
        const raw = values[f.key] ?? ''
        if (f.type === 'number') updates[f.key] = Number(raw)
        else if (f.type === 'boolean') updates[f.key] = raw === 'true'
        else updates[f.key] = raw
      }
      onSave(updates)
    } else if (input === 'q') {
      onClose()
    }
  })

  return (
    <Box flexDirection="column" borderStyle="round" borderColor={theme.border} padding={1}>
      <Text color={theme.primary} bold>
        ── Settings ──
      </Text>
      <Text dimColor>↑/↓ navigate · Enter edit · ←/→ cycle · s save · Esc close</Text>
      <Box flexDirection="column" marginTop={1}>
        {fields.map((f, i) => {
          const selectedRow = i === selected
          const val = values[f.key] ?? ''
          const displayVal =
            f.type === 'boolean' ? (val === 'true' ? '✔ yes' : '✘ no') :
            f.type === 'select' ? `[ ${val} ]` : val
          return (
            <Box key={f.key} flexDirection="row">
              <Text color={selectedRow ? theme.primary : theme.muted} bold={selectedRow}>
                {selectedRow ? '▶ ' : '  '}
              </Text>
              <Text color={selectedRow ? theme.primary : theme.text} bold={selectedRow}>
                {f.label}
              </Text>
              <Text color={theme.muted}>
                {'  '}
                {displayVal}
                {editing && selectedRow ? ' ⏎' : ''}
              </Text>
              {selectedRow && (
                <Text color={theme.muted} dimColor>
                  {'  '}({f.help ?? ''})
                </Text>
              )}
            </Box>
          )
        })}
      </Box>
    </Box>
  )
}