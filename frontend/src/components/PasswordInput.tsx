import { useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import TextInput, { type TextInputProps } from './TextInput' // <-- Added 'type' keyword

type PasswordInputProps = Omit<TextInputProps, 'type' | 'rightElement'>

export default function PasswordInput(props: PasswordInputProps) {
  const [showPassword, setShowPassword] = useState(false)

  const toggleBtn = (
    <button
      type="button"
      className="password-toggle-btn"
      onClick={() => setShowPassword(!showPassword)}
      aria-label={showPassword ? "Hide password" : "Show password"}
      tabIndex={-1}
    >
      {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
    </button>
  )

  return (
    <TextInput
      {...props}
      type={showPassword ? 'text' : 'password'}
      rightElement={toggleBtn}
    />
  )
}