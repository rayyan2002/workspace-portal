package com.bluestone.knowledge_assistant.common;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

/**
 * Turns raw {@code page}/{@code size} query parameters into a safe {@link Pageable}.
 *
 * <p>The clamp is the point. {@code ?size=1000000} is a trivially available denial of
 * service — one request that loads an entire table into memory, serialises it, and
 * holds a connection while doing so. Page size is a value the CLIENT proposes and the
 * SERVER decides, which is the same principle as never trusting a client-supplied user
 * id. A negative page index would likewise reach the database as a negative OFFSET.
 */
public final class PageRequestFactory {

    public static final int DEFAULT_SIZE = 20;
    public static final int MAX_SIZE = 100;

    private PageRequestFactory() {}

    public static Pageable of(Integer page, Integer size) {
        int safePage = (page == null || page < 0) ? 0 : page;
        int safeSize = (size == null || size < 1) ? DEFAULT_SIZE : Math.min(size, MAX_SIZE);
        return PageRequest.of(safePage, safeSize);
    }
}
