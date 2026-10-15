import type { InputHTMLAttributes, ReactNode } from 'react'

export interface TextInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  id: string
  error?: string | null
  rightElement?: ReactNode
}

export default function TextInput({
  label,
  id,
  error,
  rightElement,
  className = '',
  ...props
}: TextInputProps) {
  
  // Deduped input definition
  const inputElement = (
    <input
      id={id}
      className={`form-input ${className}`}
      aria-invalid={!!error}
      aria-describedby={error ? `${id}-error` : undefined}
      {...props}
    />
  )

  return (
    <div className="form-group">
      <label htmlFor={id} className="form-label">{label}</label>
      
      {rightElement ? (
        <div className="password-input-wrapper">
          {inputElement}
          {rightElement}
        </div>
      ) : (
        inputElement
      )}

      {error && (
        <div id={`${id}-error`} role="alert" className="form-error">
          {error}
        </div>
      )}
    </div>
  )
}