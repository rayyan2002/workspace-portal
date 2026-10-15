package com.knowledgeassistant.security;

import com.knowledgeassistant.security.jwt.JwtService;
import com.knowledgeassistant.security.userdetails.UserPrincipal;
import io.jsonwebtoken.Claims;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.List;
import java.util.UUID;

/**
 * Authenticates a request from its {@code Authorization: Bearer <jwt>} header.
 *
 * <p>This filter never rejects. It either populates the {@code SecurityContext} or leaves
 * it empty and passes the request on; the decision to answer 401 belongs to
 * {@link RestAuthenticationEntryPoint}, which is what lets permitted endpoints stay
 * reachable without a token.
 *
 * <p>The principal is reconstructed from the token's verified claims, with no database
 * lookup — that is what "stateless" buys. The cost is that a role change does not take
 * effect until the current access token expires, which is why the access TTL is minutes
 * rather than days.
 */
@Component
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private static final String BEARER_PREFIX = "Bearer ";

    private final JwtService jwtService;

    public JwtAuthenticationFilter(JwtService jwtService) {
        this.jwtService = jwtService;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {

        String token = extractBearerToken(request);

        if (token != null && SecurityContextHolder.getContext().getAuthentication() == null) {
            jwtService.parse(token).ifPresent(claims -> authenticate(claims, request));
        }

        // No MDC cleanup here on purpose. TraceIdFilter is the outermost filter and
        // already ends every request with MDC.clear(), so a second owner is redundant —
        // and actively harmful: removing userId here wiped it before RequestLoggingFilter
        // (which wraps this one) wrote its line, so every authenticated request logged
        // as "anonymous". One filter owns the MDC lifecycle.
        filterChain.doFilter(request, response);
    }

    private void authenticate(Claims claims, HttpServletRequest request) {
        UUID userId = jwtService.extractUserId(claims);
        String email = claims.get("email", String.class);

        @SuppressWarnings("unchecked")
        List<String> roles = claims.get("roles", List.class);

        UserPrincipal principal = UserPrincipal.fromClaims(userId, email, roles == null ? List.of() : roles);

        UsernamePasswordAuthenticationToken authentication =
                new UsernamePasswordAuthenticationToken(principal, null, principal.getAuthorities());
        authentication.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));

        SecurityContextHolder.getContext().setAuthentication(authentication);
        MDC.put("userId", userId.toString());
    }

    private String extractBearerToken(HttpServletRequest request) {
        String header = request.getHeader(HttpHeaders.AUTHORIZATION);
        if (header == null || !header.startsWith(BEARER_PREFIX)) {
            return null;
        }
        String token = header.substring(BEARER_PREFIX.length()).trim();
        return token.isEmpty() ? null : token;
    }
}
