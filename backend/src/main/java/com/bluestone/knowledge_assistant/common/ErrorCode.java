package com.bluestone.knowledge_assistant.common;

public enum ErrorCode {
    VALIDATION_ERROR,
    UNAUTHORIZED,
    FORBIDDEN,
    EMAIL_ALREADY_REGISTERED,
    INTERNAL_ERROR,
    BAD_REQUEST,
    MISSING_FILE,
    FILE_TOO_LARGE,
    INVALID_FILE_TYPE,
    CHAT_NOT_FOUND,
    DOCUMENT_NOT_FOUND, // Added for Document endpoint
    NOT_FOUND,
    TASK_NOT_FOUND,// Added for unmapped routes
    METHOD_NOT_ALLOWED,  // Added for wrong HTTP verbs
    RATE_LIMITED,
    AI_UNAVAILABLE,     // GenAI service down, still loading, or past its timeout (M3 D8)
    DOCUMENT_IN_USE     // Deleting it would destroy conversations that cite it (M3 D19)
}