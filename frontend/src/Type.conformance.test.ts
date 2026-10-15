import { describe, it, expect } from 'vitest'

import contract from './test/action-contract.json'
import registry from './test/tool-registry.json'
import {
  ACTION_DECISIONS,
  ACTION_PAYLOAD_KEYS,
  ACTION_RESULT_STATUSES,
  ACTION_TYPES,
  TASK_PRIORITIES,
  TASK_STATUSES,
} from './Type'

/**
 * Day 14b: the third language, finally held to the contract.
 *
 * WHY THIS FILE EXISTS. The GenAI boundary has had two conformance tests since Day 14 —
 * GenAiSpecConformanceTest against /openapi.json and ToolRegistryConformanceTest against
 * GET /tools — so Java and Python cannot drift without a build failing. The BROWSER
 * boundary had none. Type.ts was hand-written against Spring's DTOs and checked by nobody,
 * which is two of the four hand-maintained copies that produced the Month 2 drift.
 *
 * HOW IT CANNOT BE GAMED. src/test/action-contract.json is a verbatim copy of the backend's
 * src/test/resources/action-contract.json, and the backend's ActionContractSnapshotTest
 * reflects over Spring's own enums and payload records to hold Java to the same bytes.
 * Editing the snapshot to make this file pass breaks the Java test; changing Spring breaks
 * the Java test until the snapshot is regenerated, at which point this file fails until
 * Type.ts follows. Neither side can quietly win.
 *
 * WHAT IT FOUND BEFORE IT HAD EVER GUARDED ANYTHING — two real defects, both of the exact
 * kind that cannot be found by reading one language:
 *
 *   1. Spring returned an approved summary as a BARE STRING while ActionCard.tsx renders
 *      `result.summary`. That expression is `undefined` against a string, so the feature
 *      rendered an empty card with no error in any log.
 *   2. Type.ts exported `ActionStatus = 'pending' | 'approved' | 'rejected'`, matching
 *      neither of Spring's two enums; 'pending' existed nowhere in the system. It had zero
 *      consumers, which is the only reason nothing was visibly broken.
 *
 * TypeScript types erase at runtime, which is why Type.ts now exports `as const` arrays and
 * derives its unions from them. The arrays are what this file can reach; the compile-time
 * assertions in Type.ts tie them back to the interfaces, and `npm run build` runs tsc.
 */
describe('Type.ts against the backend action contract', () => {
  it('declares exactly the action types Spring does, in the same order', () => {
    expect([...ACTION_TYPES]).toEqual(contract.actionTypes)
  })

  it('declares the decision vocabulary Spring accepts', () => {
    expect([...ACTION_DECISIONS]).toEqual(contract.decisions)
  })

  it('declares the result statuses Spring returns, not the decisions', () => {
    // The one that was wrong. These are two different vocabularies and the old
    // `ActionStatus` type conflated them while matching neither.
    expect([...ACTION_RESULT_STATUSES]).toEqual(contract.statuses)
    expect(ACTION_RESULT_STATUSES).not.toContain('pending')
    expect(ACTION_RESULT_STATUSES).not.toContain('approved')
  })

  it('declares the priorities and task statuses Spring serialises', () => {
    expect([...TASK_PRIORITIES]).toEqual(contract.priorities)
    // in-progress with a hyphen: Spring's TaskStatus.in_progress goes through @JsonValue,
    // so the enum NAME never reaches the browser.
    expect([...TASK_STATUSES]).toEqual(contract.taskStatuses)
    expect(TASK_STATUSES).not.toContain('in_progress')
  })

  it.each(Object.keys(ACTION_PAYLOAD_KEYS) as (keyof typeof ACTION_PAYLOAD_KEYS)[])(
    'sends the payload Spring expects for %s',
    (type) => {
      expect([...ACTION_PAYLOAD_KEYS[type]]).toEqual(
        contract.payloads[type as keyof typeof contract.payloads],
      )
    },
  )

  it('has a payload for every action type and no orphans', () => {
    // A fourth action added to one place and not the other fails here. summarize-document
    // spent five days published, validated and unproposable because exactly this kind of
    // two-place change was only made in one place.
    expect(Object.keys(ACTION_PAYLOAD_KEYS).sort()).toEqual([...ACTION_TYPES].sort())
    expect(Object.keys(contract.payloads).sort()).toEqual([...ACTION_TYPES].sort())
  })
})

describe('Type.ts against the published GenAI tool registry', () => {
  const published = registry.tools.map((t) => t.name)

  it('names the same three tools the GenAI service publishes', () => {
    // The ONLY part of the action contract all three languages must spell identically.
    // These literals reach Postgres (action_audit.type), Jackson's deserialisation, Python's
    // ToolName enum and this file's discriminated union.
    expect([...ACTION_TYPES].sort()).toEqual([...published].sort())
  })

  it('uses hyphens, because the running system does', () => {
    // The training tracker writes these with underscores. The running system does not, and
    // `create_task` is a rejected discriminator tag on both of the other two sides.
    for (const type of ACTION_TYPES) {
      expect(type).toContain('-')
      expect(type).not.toContain('_')
    }
  })

  it('does not expect the model-facing argument names on the browser wire', () => {
    // NOT A CONTRADICTION, and worth asserting so nobody "fixes" it. GET /tools publishes
    // what a MODEL may produce — summarize-document carries a chunk_ordinal, because a 0.5B
    // model must never be asked for a UUID (36 tokens, and it measurably stops citing at
    // all). The browser exchanges Spring's shape. ActionProposer is the bridge, and the
    // backend's ToolRegistryConformanceTest is what proves the bridge exists.
    const summarize = registry.tools.find((t) => t.name === 'summarize-document')!
    const modelFacing = Object.keys(summarize.arguments_schema.properties)

    expect(modelFacing).toContain('chunk_ordinal')
    expect(ACTION_PAYLOAD_KEYS['summarize-document']).not.toContain('chunk_ordinal')
    // The field Spring resolves the ordinal INTO must be published, or nothing can bridge it.
    expect(modelFacing).toContain('document_id')
  })

  it.each(['create-task', 'lookup-knowledge'] as const)(
    'agrees with the model-facing argument names for %s, where all three sides match',
    (tool) => {
      // These two tools have no translation step: Python's argument names, Spring's payload
      // fields and this union are the same strings. Asserting it means a rename on any of
      // the three sides fails a build rather than failing a user.
      const schema = registry.tools.find((t) => t.name === tool)!.arguments_schema
      const args = Object.keys(schema.properties).filter((k) => k !== 'tool')

      expect([...ACTION_PAYLOAD_KEYS[tool]].sort()).toEqual(args.sort())
    },
  )
})
