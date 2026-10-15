import type { Document, ChatSession, Message, Task, ActionAudit } from '../Type'

export const DEMO_CREDENTIALS = {
  email: 'developer@example.com',
  password: 'Password123!'
}

export const mockUser = {
  id: 'usr-99',
  email: 'developer@example.com',
  name: 'Muhammad Rayyan Ayub'
}

export const mockDocuments: Document[] = [
  {
    id: 'doc-1',
    filename: 'quarterly_financial_report.pdf',
    sizeBytes: 2411724,
    uploadDate: '2026-07-01T10:00:00.000Z',
    status: 'ready'
  },
  {
    id: 'doc-2',
    filename: 'system_architecture_blueprint.png',
    sizeBytes: 5242880,
    uploadDate: '2026-07-02T14:30:00.000Z',
    status: 'processing'
  },
  {
    id: 'doc-3',
    filename: 'legacy_data_dictionary.csv',
    sizeBytes: 104857,
    uploadDate: '2026-07-03T09:15:00.000Z',
    status: 'failed'
  },
  {
    id: 'doc-101',
    filename: 'aerotwin_telemetry_spec_v2.pdf',
    sizeBytes: 1048576,
    uploadDate: '2026-07-10T09:15:00.000Z',
    status: 'ready'
  },
  {
    id: 'doc-102',
    filename: 'FastAPI_Proxy_Architecture.md',
    sizeBytes: 45020,
    uploadDate: '2026-07-11T14:20:00.000Z',
    status: 'ready'
  },
  {
    id: 'doc-103',
    filename: 'maintenance_log_Q2.md',
    sizeBytes: 85000,
    uploadDate: '2026-07-12T08:00:00.000Z',
    status: 'ready'
  }
]

export const mockChatSessions: ChatSession[] = [
  {
    id: 'chat-1',
    title: 'AeroTwin Health Metrics',
    lastMessagePreview: 'The RUL pipeline completed its run over the telemetry arrays.',
    updatedAt: '2026-07-07T11:00:00.000Z'
  },
  {
    id: 'chat-2',
    title: 'FastAPI Proxy Architecture',
    lastMessagePreview: 'Update the middleware parameters to allow cross-origin requests.',
    updatedAt: '2026-07-06T15:45:00.000Z'
  }
]

export const mockChatMessages: Record<string, Message[]> = {
  'chat-1': [
    {
      id: 'msg-101',
      content: 'Can you verify the status of the AeroTwin remaining useful life calculation rules?',
      sender: 'user',
      timestamp: '2026-07-07T10:55:00.000Z'
    },
    {
      id: 'msg-102',
      content: 'The RUL pipeline completed its run over the telemetry arrays. System health reads green.',
      sender: 'assistant',
      timestamp: '2026-07-07T11:00:00.000Z'
    }
  ],
  'chat-2': [
    {
      id: 'msg-201',
      content: 'Why is the React client blocking pre-flight options when connecting to the API routes?',
      sender: 'user',
      timestamp: '2026-07-06T15:40:00.000Z'
    },
    {
      id: 'msg-202',
      content: 'Update the middleware parameters to allow cross-origin requests natively inside your gateway proxy configurations.',
      sender: 'assistant',
      timestamp: '2026-07-06T15:45:00.000Z'
    }
  ]
}

// ==========================================================================
// DAY 13/14: Action Persistence & Audit Arrays (Strictly Typed)
// ==========================================================================
export const mockTasks: Task[] = [
  {
    id: 'task-seed-1',
    title: 'Monitor compressor stage wear tolerances',
    priority: 'medium',
    status: 'todo',
    createdAt: '2026-07-07T11:05:00.000Z',
    sourceSessionId: 'chat-1'
  },
  {
    id: 'task-seed-2',
    title: 'Update gateway proxy CORS middleware',
    priority: 'high',
    status: 'done',
    createdAt: '2026-07-06T15:50:00.000Z',
    completedAt: '2026-07-08T09:00:00.000Z',
    sourceSessionId: 'chat-2'
  },
  {
    id: 'task-seed-3',
    title: 'Review AeroTwin RUL pipeline logs',
    priority: 'low',
    status: 'in-progress',
    createdAt: '2026-07-07T11:30:00.000Z',
    sourceSessionId: 'chat-1'
  }
];

// Update to mockActionAudit in src/mocks/db.ts
export const mockActionAudit: ActionAudit[] = [
  {
    id: 'audit-seed-1', actionId: 'act-seed-1', sessionId: 'chat-1',
    type: 'create-task', decision: 'approved', timestamp: '2026-07-07T11:05:00.000Z'
  },
  {
    id: 'audit-seed-2', actionId: 'act-seed-2', sessionId: 'chat-1',
    type: 'summarize-document', decision: 'rejected', timestamp: '2026-07-07T11:10:00.000Z'
  },
  // NEW: Corroborating record for task-seed-2
  {
    id: 'audit-seed-3', actionId: 'act-seed-3', sessionId: 'chat-2',
    type: 'create-task', decision: 'approved', timestamp: '2026-07-06T15:50:00.000Z'
  },
  // NEW: Corroborating record for task-seed-3
  {
    id: 'audit-seed-4', actionId: 'act-seed-4', sessionId: 'chat-1',
    type: 'create-task', decision: 'approved', timestamp: '2026-07-07T11:30:00.000Z'
  }
];