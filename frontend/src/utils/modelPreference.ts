import type { GenerationModel } from '../Type'

const KEY = 'ka.generationModel'

/**
 * The chosen model, remembered across remounts and reloads.
 *
 * WHY THIS IS STORED AT ALL. It used to be `useState('local')` inside MessageView, with a
 * comment calling it "per question, not a saved preference". The intent was good — the
 * choice decides whether document text leaves the machine, so it should be visible at the
 * moment of asking — but the consequence was that ANY remount silently reverted a user who
 * had deliberately chosen Cloud back to on-device, mid-conversation, with no indication.
 * Reported from real use, and the trace log confirms it: one conversation ran
 * `gemini (0 history) → local (2 history)` without the user touching the selector.
 *
 * Component state was the wrong home for a decision that has to outlive a component.
 *
 * THE DEFAULT IS STILL `local`, and that part was right: a user who has never chosen gets
 * the private option. What changes is that a user who HAS chosen keeps their choice.
 *
 * THE TRADE, written down rather than discovered later: once Cloud is selected it stays
 * selected until changed — including after a reload, and for every later conversation. That
 * is what "it should remain to that model" asks for, and it means document text keeps going
 * to Google until someone switches back. The selector sits next to the message box, showing
 * the current choice on every single question, which is what keeps that honest.
 */
export function readStoredModel(): GenerationModel {
  try {
    const stored = localStorage.getItem(KEY)
    return stored === 'gemini' || stored === 'local' ? stored : 'local'
  } catch {
    // Private browsing, or storage disabled. Fall back to the safe default rather than
    // letting a storage failure break the chat.
    return 'local'
  }
}

export function storeModel(model: GenerationModel): void {
  try {
    localStorage.setItem(KEY, model)
  } catch {
    // Not remembering is a degraded experience; throwing here would lose the message.
  }
}
