import { http, HttpResponse, delay } from 'msw'
import { mockDocuments, DEMO_CREDENTIALS, mockUser, mockChatSessions, mockChatMessages, mockTasks, mockActionAudit } from './db'
import { MAX_FILE_SIZE_BYTES, ALLOWED_MIME_TYPES } from '../Type'
import type { APIError, AuthResponse, LoginRequest, Citation, ActionProposal, ActionRequest, ActionResult, Task, ActionAudit } from '../Type'

// ==========================================================================
// HELPER: DRY AI Response Generator
// ==========================================================================
function generateAIResponse(content: string) {
  const lowerContent = content.toLowerCase()
  let responseContent = ''
  let dummyCitations: Citation[] = []
  let dummyActions: ActionProposal[] = []

  if (lowerContent.includes('health') || lowerContent.includes('aerotwin')) {
    responseContent = 'The AeroTwin RUL pipeline has completed its analysis. The telemetry arrays indicate system health is currently green, with no anomalies detected in the compressor stages.'
    dummyCitations = [
      {
        id: 'cit-1', documentId: 'doc-101', documentName: 'aerotwin_telemetry_spec_v2.pdf', 
        section: 'Section 4.1: Compressor Thresholds',
        excerpt: 'Telemetry arrays must report green status across all primary compressor stages before the RUL pipeline can finalize the diagnostic run.'
      },
      {
        id: 'cit-2', documentId: 'doc-103', documentName: 'maintenance_log_Q2.md',
        section: 'Hardware Diagnostics',
        excerpt: 'Compressor stage wear remains within the 5% tolerance margin, requiring no immediate intervention.'
      }
    ]
    dummyActions = [{
      id: `act-${Date.now()}-1`,
      type: 'create-task',
      label: 'Create follow-up task to monitor compressor stage wear tolerances.',
      payload: { title: 'Monitor compressor stage wear tolerances', priority: 'medium' }
    }]
  } 
  else if (lowerContent.includes('api') || lowerContent.includes('cors')) {
    responseContent = 'The React client is blocking pre-flight options because the FastAPI backend lacks the appropriate CORS middleware. You need to update the origins list in your gateway proxy configurations.'
    dummyCitations = [{
      id: 'cit-3', documentId: 'doc-102', documentName: 'FastAPI_Proxy_Architecture.md',
      section: 'Middleware Config',
      excerpt: 'If the React client fails on pre-flight OPTIONS requests, ensure the CORSMiddleware is explicitly injected with the correct allowed origins.'
    }]
    dummyActions = [{
      id: `act-${Date.now()}-2`,
      type: 'lookup-knowledge',
      label: 'Search knowledge base for internal gateway proxy CORS standards.',
      payload: { query: 'gateway proxy CORS middleware standards' }
    }]
  } 
  else if (lowerContent.includes('summarize') || lowerContent.includes('summary')) {
    responseContent = 'I can run a full analysis and generate a comprehensive summary of the Q3 financial metrics for you.'
    dummyActions = [{
      id: `act-${Date.now()}-3`,
      type: 'summarize-document',
      label: 'Generate a structured summary of quarterly_financial_report.pdf',
      payload: { documentId: 'doc-1', documentName: 'quarterly_financial_report.pdf' }
    }]
  }
  else {
    responseContent = 'Based on the uploaded documentation, the system parameters are operating within expected thresholds. Let me know if you need to extract specific metrics.'
    dummyCitations = [{
      id: 'cit-4', documentId: 'doc-1', documentName: 'quarterly_financial_report.pdf',
      section: 'Executive Summary',
      excerpt: 'All system parameters and financial metrics have remained within the expected thresholds for Q3.'
    }]
  }

  return { responseContent, dummyCitations, dummyActions }
}


/**
 * Contract revision #2 — list endpoints return { items, total, page, size }.
 *
 * These handlers ARE the frontend's copy of the contract, and they are the third
 * copy to drift: the real API changed shape on Day 16 and Day 19, and nothing
 * updated them. The tests that depend on them have been red ever since — a working
 * safety net, disconnected, because no `npm test` script existed to run it.
 */
function paged<T>(items: T[]) {
  return { items, total: items.length, page: 0, size: 20 }
}

export const handlers = [
  http.get('/api/health', () => {
    return HttpResponse.json({ status: 'ok' })
  }),

  http.get('/api/documents', async ({ request }) => {
    await delay(800)

    const url = new URL(request.url)
    const scenario = url.searchParams.get('scenario')

    if (scenario === 'error') {
      return new HttpResponse(null, { status: 500 })
    }

    if (scenario === 'empty') {
      return HttpResponse.json(paged([]))
    }

    return HttpResponse.json(paged(mockDocuments))
  }),

  http.get('/api/documents/:documentId', async ({ params }) => {
    await delay(400)
    
    const { documentId } = params

    if (documentId === 'invalid-id-test') {
      const badRequestError: APIError = {
        message: 'The provided document ID format is invalid.',
        code: 'INVALID_DOCUMENT_ID'
      }
      return HttpResponse.json(badRequestError, { status: 400 })
    }

    const document = mockDocuments.find(doc => doc.id === documentId)

    if (!document) {
      const notFoundError: APIError = {
        message: `Document with ID ${documentId} not found.`,
        code: 'DOCUMENT_NOT_FOUND'
      }
      return HttpResponse.json(notFoundError, { status: 404 })
    }

    return HttpResponse.json(document)
  }),

  http.post('/api/auth/login', async ({ request }) => {
    await delay(600)
    
    let body: unknown
    try {
      body = await request.json()
    } catch {
      const badJsonError: APIError = { message: 'Malformed JSON payload.', code: 'BAD_REQUEST' }
      return HttpResponse.json(badJsonError, { status: 400 })
    }

    const loginBody = body as LoginRequest
    const { email, password } = loginBody

    if (!email || !password) {
      const missingFieldsError: APIError = { 
        message: 'Email and password fields are required.', 
        code: 'MISSING_FIELDS' 
      }
      return HttpResponse.json(missingFieldsError, { status: 400 })
    }

    const normalizedEmail = email.trim().toLowerCase()
    const expectedEmail = DEMO_CREDENTIALS.email.toLowerCase()

    if (normalizedEmail !== expectedEmail || password !== DEMO_CREDENTIALS.password) {
      const authError: APIError = { 
        message: 'Invalid email or password.', 
        code: 'UNAUTHORIZED' 
      }
      return HttpResponse.json(authError, { status: 401 })
    }

    const successResponse: AuthResponse = {
      accessToken: 'mock-access-token-example-xyz123',
      refreshToken: 'mock-refresh-token-example-xyz123',
      tokenType: 'Bearer',
      expiresIn: 900,
      user: mockUser,
      roles: ['ROLE_USER', 'ROLE_ADMIN']
    }

    return HttpResponse.json(successResponse, { status: 200 })
  }),

  http.post('/api/documents/upload', async ({ request }) => {
    const url = new URL(request.url)
    const scenario = url.searchParams.get('scenario')

    if (scenario === 'error') {
      return new HttpResponse(null, { status: 500 })
    }

    let formData: FormData
    try {
      formData = await request.formData()
    } catch {
      const badFormError: APIError = { message: 'Invalid form data payload.', code: 'BAD_REQUEST' }
      return HttpResponse.json(badFormError, { status: 400 })
    }

    const file = formData.get('file') as File | null

    if (!file) {
      const noFileError: APIError = { message: 'No file found in the upload payload.', code: 'MISSING_FILE' }
      return HttpResponse.json(noFileError, { status: 400 })
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
      const sizeError: APIError = { message: 'File size exceeds the 10 MB ceiling constraint.', code: 'FILE_TOO_LARGE' }
      return HttpResponse.json(sizeError, { status: 400 })
    }

    const fallbackExtensions = ['.md', '.markdown', '.csv', '.xlsx']
    const hasValidExtension = fallbackExtensions.some(ext => file.name.toLowerCase().endsWith(ext))
    const isValidType = ALLOWED_MIME_TYPES.includes(file.type) || hasValidExtension

    if (!isValidType) {
      const typeError: APIError = { message: 'Unsupported file format. Please upload PDF, TXT, DOCX, MD, CSV, or XLSX.', code: 'INVALID_FILE_TYPE' }
      return HttpResponse.json(typeError, { status: 400 })
    }

    const newDocument = {
      id: `doc-${Math.random().toString(36).slice(2, 11)}`,
      filename: file.name,
      sizeBytes: file.size,
      uploadDate: new Date().toISOString(),
      status: 'pending' as const
    }

    return HttpResponse.json(newDocument, { status: 201 })
  }),

  http.get('/api/chat/sessions', async ({ request }) => {
    await delay(300)
    const url = new URL(request.url)
    const scenario = url.searchParams.get('scenario')

    if (scenario === 'error') {
      return new HttpResponse(null, { status: 500 })
    }
    if (scenario === 'empty') {
      return HttpResponse.json(paged([]))
    }

    return HttpResponse.json(paged(mockChatSessions))
  }),

  http.get('/api/chat/:sessionId/messages', async ({ params }) => {
    await delay(400)
    const { sessionId } = params as { sessionId: string }

    const messages = mockChatMessages[sessionId]
    if (!messages) {
      const notFoundError: APIError = {
        message: 'The requested conversation thread history could not be found.',
        code: 'CHAT_NOT_FOUND'
      }
      return HttpResponse.json(notFoundError, { status: 404 })
    }

    return HttpResponse.json(messages)
  }),

  http.post('/api/chat/sessions', async ({ request }) => {
    const delayMs = Math.floor(Math.random() * 1000) + 1000
    await delay(delayMs)

    let body: unknown
    try { body = await request.json() } catch { return HttpResponse.json({ message: 'Malformed JSON.' }, { status: 400 }) }
    
    const { initialMessage } = body as { initialMessage?: string }

    if (!initialMessage) {
      return HttpResponse.json({ message: 'initialMessage is required for lazy session creation.' }, { status: 400 })
    }

    const newSessionId = `chat-${Math.random().toString(36).slice(2, 9)}`
    const timestamp = new Date().toISOString()
    
    const aiResult = generateAIResponse(initialMessage)

    const userMsg = {
      id: `msg-usr-${Date.now()}`,
      content: initialMessage,
      sender: 'user' as const,
      timestamp: new Date(Date.now() - delayMs).toISOString()
    }
    
    const assistantMsg = {
      id: `msg-${Math.random().toString(36).slice(2, 11)}`,
      content: aiResult.responseContent,
      sender: 'assistant' as const,
      timestamp: timestamp,
      citations: aiResult.dummyCitations,
      actions: aiResult.dummyActions
    }

    const messages = [userMsg, assistantMsg]
    const derivedTitle = initialMessage.length > 30 ? `${initialMessage.substring(0, 30)}...` : initialMessage
    
    const newSession = {
      id: newSessionId,
      title: derivedTitle,
      lastMessagePreview: assistantMsg.content.substring(0, 60) + '...',
      updatedAt: timestamp
    }

    mockChatSessions.unshift(newSession)
    mockChatMessages[newSessionId] = messages

    return HttpResponse.json({ session: newSession, messages: messages }, { status: 201 })
  }),

  http.post('/api/chat/message', async ({ request }) => {
    const delayMs = Math.floor(Math.random() * 1000) + 1500;
    await delay(delayMs);

    const url = new URL(request.url)
    if (url.searchParams.get('scenario') === 'error') {
      return new HttpResponse(null, { status: 500 })
    }

    let body: unknown
    try {
      body = await request.json()
    } catch {
      return HttpResponse.json({ message: 'Malformed JSON.' }, { status: 400 })
    }

    const { sessionId, content } = body as { sessionId: string, content: string }
    if (!sessionId || !content) {
      return HttpResponse.json({ message: 'Missing sessionId or content.' }, { status: 400 })
    }

    const aiResult = generateAIResponse(content)

    const userMessage = {
      id: `msg-usr-${Date.now()}`,
      content: content,
      sender: 'user' as const,
      timestamp: new Date(Date.now() - delayMs).toISOString()
    }

    const assistantMessage = {
      id: `msg-${Math.random().toString(36).slice(2, 11)}`,
      content: aiResult.responseContent,
      sender: 'assistant' as const,
      timestamp: new Date().toISOString(),
      citations: aiResult.dummyCitations,
      actions: aiResult.dummyActions
    }

    if (!mockChatMessages[sessionId]) {
      mockChatMessages[sessionId] = []
    }
    mockChatMessages[sessionId].push(userMessage, assistantMessage)
    const activeSession = mockChatSessions.find(s => s.id === sessionId)
    if (activeSession) {
      activeSession.updatedAt = assistantMessage.timestamp
      activeSession.lastMessagePreview = assistantMessage.content.substring(0, 60) + '...'
    }

    return HttpResponse.json(assistantMessage, { status: 200 })
  }),

  http.post('/api/ai/actions', async ({ request }) => {
    await delay(800)

    const url = new URL(request.url)
    if (url.searchParams.get('scenario') === 'error') return new HttpResponse(null, { status: 500 })

    let body: unknown
    try {
      body = await request.json()
    } catch {
      return HttpResponse.json({ message: 'Malformed JSON.' }, { status: 400 })
    }

    const req = body as ActionRequest;

    if (!req.actionId || !req.decision || !req.type) {
      return HttpResponse.json({ message: 'Missing required action parameters.' }, { status: 400 })
    }

    const auditRecord: ActionAudit = {
      id: `audit-${Date.now()}`,
      actionId: req.actionId,
      sessionId: req.sessionId,
      type: req.type,
      decision: req.decision,
      timestamp: new Date().toISOString()
    }
    mockActionAudit.push(auditRecord)

    if (req.decision === 'rejected') {
      return HttpResponse.json({
        actionId: req.actionId,
        status: 'rejected',
        result: null
      } as ActionResult, { status: 200 })
    }

    if (req.type === 'create-task') {
      const newTask: Task = {
        id: `task-${Math.random().toString(36).slice(2, 11)}`,
        title: req.payload.title,
        priority: req.payload.priority,
        status: 'todo',
        createdAt: new Date().toISOString(),
        sourceSessionId: req.sessionId 
      }
      mockTasks.push(newTask)
      return HttpResponse.json({
        actionId: req.actionId,
        status: 'completed',
        type: 'create-task',
        result: newTask
      } as ActionResult, { status: 200 })
    } 
    else if (req.type === 'summarize-document') {
      return HttpResponse.json({
        actionId: req.actionId,
        status: 'completed',
        type: 'summarize-document',
        result: { summary: `Executive Summary: Document ${req.payload.documentName} indicated...` }
      } as ActionResult, { status: 200 })
    } 
    else if (req.type === 'lookup-knowledge') {
      return HttpResponse.json({
        actionId: req.actionId,
        status: 'completed',
        type: 'lookup-knowledge',
        result: { snippets: ['[Internal Wiki] To allow cross-origin requests...'] }
      } as ActionResult, { status: 200 })
    }

    return HttpResponse.json({ message: 'Unknown action type.' }, { status: 400 })
  }),

  http.get('/api/tasks', async ({ request }) => {
    await delay(600)
    const url = new URL(request.url)
    if (url.searchParams.get('scenario') === 'error') {
      return new HttpResponse(null, { status: 500 })
    }
    return HttpResponse.json(paged(mockTasks))
  }),

  http.get('/api/actions/audit', async ({ request }) => {
    await delay(500)
    const url = new URL(request.url)
    if (url.searchParams.get('scenario') === 'error') {
      return new HttpResponse(null, { status: 500 })
    }
    return HttpResponse.json(paged(mockActionAudit))
  }), 

  // ==========================================================================
  // UPDATED: PATCH Task Status (Update existing resource)
  // ==========================================================================
  http.patch('/api/tasks/:taskId', async ({ request, params }) => {
    const delayMs = Math.floor(Math.random() * 500) + 500 // Added delay for optimistic UI
    await delay(delayMs)

    const url = new URL(request.url)
    if (url.searchParams.get('scenario') === 'error') {
      return new HttpResponse(null, { status: 500 }) // Added error toggle
    }

    const { taskId } = params
    const body = await request.json() as { status: Task['status'] }
    
    const taskIndex = mockTasks.findIndex(t => t.id === taskId)
    if (taskIndex === -1) {
      return HttpResponse.json({ message: 'Task not found' }, { status: 404 })
    }

    const currentTask = mockTasks[taskIndex]
    const updatedTask = {
      ...currentTask,
      status: body.status,
    }

    // Explicitly manage the side-effect
    if (body.status === 'done') {
      updatedTask.completedAt = new Date().toISOString()
    } else {
      delete updatedTask.completedAt // Fully clear it on reopen
    }
    
    mockTasks[taskIndex] = updatedTask
    
    return HttpResponse.json(updatedTask, { status: 200 })
  }),

  http.delete('/api/documents/:documentId', async ({ request, params }) => {
    const delayMs = Math.floor(Math.random() * 500) + 500
    await delay(delayMs)

    const url = new URL(request.url)
    if (url.searchParams.get('scenario') === 'error') {
      return new HttpResponse(null, { status: 500 })
    }

    const { documentId } = params

    const docIndex = mockDocuments.findIndex(doc => doc.id === documentId)

    if (docIndex === -1) {
      const notFoundError: APIError = {
        message: `Document with ID ${documentId} could not be found for deletion.`,
        code: 'DOCUMENT_NOT_FOUND'
      }
      return HttpResponse.json(notFoundError, { status: 404 })
    }

    mockDocuments.splice(docIndex, 1)

    return HttpResponse.json({ 
      success: true, 
      deletedId: documentId,
      message: 'Document successfully deleted.'
    }, { status: 200 })
  })
]