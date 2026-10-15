package com.bluestone.knowledge_assistant.common.dto;

import org.springframework.data.domain.Page;

import java.util.List;
import java.util.function.Function;

/**
 * The paged list envelope the contract reserved on Day 6.
 *
 * <p>Deferred at the time because adopting it needs a synchronised frontend change; it
 * comes due now because every list endpoint returned its entire table. At demo volume
 * that was 39KB of documents and 83KB of audit rows in a single response, growing
 * without bound — a workspace with a year of history would have returned all of it,
 * every time the page loaded.
 *
 * <p>Deliberately NOT Spring Data's own {@code Page} serialisation. That exposes
 * Pageable internals ({@code pageable}, {@code sort}, {@code numberOfElements},
 * {@code first}, {@code last}) and its JSON shape has changed between Spring versions —
 * Boot even warns about serialising it directly. Four fields the frontend agreed to is
 * a contract; whatever Spring Data happens to emit is not.
 *
 * @param items   the rows for this page
 * @param total   total matching rows across all pages, so the UI can size a pager
 * @param page    zero-based page index, echoed back so a response is self-describing
 * @param size    page size actually applied, which may be lower than requested
 */
public record PageResponse<T>(
        List<T> items,
        long total,
        int page,
        int size
) {
    /** Maps a Spring Data page of entities into an envelope of DTOs. */
    public static <E, D> PageResponse<D> from(Page<E> page, Function<E, D> toDto) {
        return new PageResponse<>(
                page.getContent().stream().map(toDto).toList(),
                page.getTotalElements(),
                page.getNumber(),
                page.getSize());
    }
}
