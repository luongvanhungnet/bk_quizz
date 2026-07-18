package com.genquiz.bk.common.web;

import tools.jackson.databind.ObjectMapper;
import com.genquiz.bk.common.api.ApiEnvelope;
import com.genquiz.bk.common.api.ApiFieldError;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 20)
@ConditionalOnProperty(name = "bkquiz.rate-limit.enabled", havingValue = "true", matchIfMissing = true)
public class RateLimitFilter extends OncePerRequestFilter {
    private final ConcurrentHashMap<String, Window> windows = new ConcurrentHashMap<>();
    private final ObjectMapper mapper;
    public RateLimitFilter(ObjectMapper mapper) { this.mapper = mapper; }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        Policy policy = policy(request);
        String key = policy.name + ":" + clientIp(request);
        Instant now = Instant.now();
        Window window = windows.compute(key, (ignored, existing) ->
                existing == null || existing.resetAt.isBefore(now)
                        ? new Window(1, now.plus(policy.duration)) : existing.increment());
        response.setHeader("X-RateLimit-Limit", Integer.toString(policy.limit));
        response.setHeader("X-RateLimit-Remaining", Integer.toString(Math.max(0, policy.limit - window.count)));
        if (window.count > policy.limit) {
            long retry = Math.max(1, Duration.between(now, window.resetAt).toSeconds());
            response.setStatus(429);
            response.setHeader("Retry-After", Long.toString(retry));
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            mapper.writeValue(response.getWriter(), ApiEnvelope.failure("Bạn thao tác quá nhanh. Vui lòng thử lại sau.",
                    List.of(new ApiFieldError("RATE_LIMITED", "Bạn thao tác quá nhanh. Vui lòng thử lại sau.")),
                    (String) request.getAttribute("traceId")));
            return;
        }
        chain.doFilter(request, response);
        if (windows.size() > 50_000) windows.entrySet().removeIf(entry -> entry.getValue().resetAt.isBefore(now));
    }

    private Policy policy(HttpServletRequest request) {
        String path = request.getRequestURI();
        if ("POST".equals(request.getMethod()) && path.equals("/api/auth/login")) return new Policy("login", 5, Duration.ofMinutes(15));
        if ("POST".equals(request.getMethod()) && path.equals("/api/auth/register")) return new Policy("register", 3, Duration.ofHours(1));
        if ("POST".equals(request.getMethod()) && path.equals("/api/auth/verify-email/resend")) return new Policy("verification-resend", 3, Duration.ofMinutes(15));
        if (path.equals("/api/quizzes/generate") || path.contains("/chat/")) return new Policy("ai", 10, Duration.ofHours(1));
        return new Policy("general:" + request.getMethod() + ":" + normalizedPath(path),
                300, Duration.ofMinutes(15));
    }

    private String normalizedPath(String path) {
        return path.replaceAll("(?i)/[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}(?=/|$)",
                "/{id}");
    }

    private String clientIp(HttpServletRequest request) {
        String forwarded = request.getHeader("X-Forwarded-For");
        return forwarded == null ? request.getRemoteAddr() : forwarded.split(",", 2)[0].trim();
    }
    private record Policy(String name, int limit, Duration duration) {}
    private record Window(int count, Instant resetAt) { Window increment() { return new Window(count + 1, resetAt); } }
}
