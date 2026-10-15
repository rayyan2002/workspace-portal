package com.bluestone.knowledge_assistant.action.dto;

import java.util.List;

/**
 * What an approved {@code lookup-knowledge} returns: the matching passages, not an answer.
 *
 * <p>Shape taken from the frontend's {@code ActionResult} union, which declares
 * {@code result: { snippets: string[] }} and renders {@code result.snippets[0]} — written
 * in Month 2 against a backend branch that returned a placeholder string and reported
 * success. Day 14b makes the backend match what was already published rather than changing
 * the published shape to match a stub.
 */
public record LookupResult(List<String> snippets) {}
