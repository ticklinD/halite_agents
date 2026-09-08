import React, { useState } from 'react'
import { Box, Text, useInput } from 'ink'

type Props = {
  onSubmit: (text: string) => void
  disabled?: boolean
}

export function InputBar({ onSubmit, disabled }: Props) {
  const [value, setValue] = useState('')
  const [cursorVisible, setCursorVisible] = useState(true)

  useInput((input, key) => {
    if (disabled) return

    if (key.return) {
      if (value.trim()) {
        onSubmit(value.trim())
        setValue('')
      }
      return
    }

    if (key.backspace || key.delete) {
      setValue(v => v.slice(0, -1))
      return
    }

    if (key.ctrl && input === 'c') {
      process.exit(0)
    }

    // Regular character
    if (input && !key.ctrl && !key.meta) {
      setValue(v => v + input)
    }
  })

  return (
    <Box>
      <Text color="cyan" bold>{'>'} </Text>
      <Text color={disabled ? 'gray' : 'white'}>
        {value}
      </Text>
      {!disabled && (
        <Text color="cyan" inverse>{' '}</Text>
      )}
    </Box>
  )
}
