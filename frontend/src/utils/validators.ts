export function isRequired(value: string): boolean {
  return value.trim().length > 0
}

export function isValidEmail(email: string): boolean {
  // Pragmatic check: text + @ + text + . + text
  // Defers RFC-complete validation to the server
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}