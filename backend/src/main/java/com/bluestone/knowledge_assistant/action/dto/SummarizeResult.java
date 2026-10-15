package com.bluestone.knowledge_assistant.action.dto;

/**
 * What an approved {@code summarize-document} returns. Day 14b.
 *
 * <p><strong>This wrapper exists because its absence was a live defect.</strong>
 * {@code ActionService} returned the summary as a BARE STRING, while the frontend's
 * {@code ActionResult} union declares {@code result: { summary: string }} and
 * {@code ActionCard.tsx} renders {@code actionResponse.result.summary}. Against a bare
 * string that expression is {@code undefined}, so an approved summary rendered as an empty
 * card — no error anywhere, just nothing on screen.
 *
 * <p>Found by building the frontend conformance test rather than by anyone using the
 * feature, which is the argument for having built it: this is the third language in the
 * contract and it had no test holding it to the other two.
 */
public record SummarizeResult(String summary) {}
