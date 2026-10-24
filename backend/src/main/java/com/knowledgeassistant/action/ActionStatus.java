package com.knowledgeassistant.action;

/**
 * What EXECUTION did, as distinct from what the human DECIDED.
 *
 * <p>{@code running} arrived with V22. A decision is acknowledged instantly; the work it
 * causes may take minutes, and summarising runs a full grounded-answer pass over a language
 * model. Without an in-flight value an approved action would be invisible between the click
 * and the result, so the request used to hold the connection open for 78-135 seconds to
 * avoid admitting it had nowhere to put the state.
 */
public enum ActionStatus { completed, rejected, failed, running }
