package com.genquiz.bk.security;

import tools.jackson.databind.ObjectMapper;
import com.genquiz.bk.common.api.ApiEnvelope;
import com.genquiz.bk.common.api.ApiFieldError;
import com.genquiz.bk.config.AppProperties;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;
import java.util.Set;

@Component
public class CookieCsrfFilter extends OncePerRequestFilter {
    private final AppProperties properties;
    private final ObjectMapper objectMapper;
    private static final Set<String> PROTECTED_ROUTES = Set.of(
            "/api/auth/refresh-token", "/api/auth/logout", "/api/auth/logout-all");

    public CookieCsrfFilter(AppProperties properties, ObjectMapper objectMapper) {
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !"POST".equalsIgnoreCase(request.getMethod()) || !PROTECTED_ROUTES.contains(request.getRequestURI());
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        String origin = request.getHeader("Origin");
        Set<String> allowed = Set.copyOf(properties.frontendOrigins());
        String cookie = cookie(request, properties.security().xsrfCookieName());
        String header = request.getHeader("X-XSRF-TOKEN");
        boolean originValid = origin == null || allowed.contains(origin);
        boolean tokenValid = cookie != null && header != null && MessageDigest.isEqual(
                cookie.getBytes(StandardCharsets.UTF_8), header.getBytes(StandardCharsets.UTF_8));
        if (!originValid || !tokenValid) {
            response.setStatus(HttpServletResponse.SC_FORBIDDEN);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            objectMapper.writeValue(response.getWriter(), ApiEnvelope.failure("Yêu cầu bảo mật không hợp lệ.",
                    List.of(new ApiFieldError("CSRF_INVALID", "Yêu cầu bảo mật không hợp lệ.")),
                    (String) request.getAttribute("traceId")));
            return;
        }
        chain.doFilter(request, response);
    }

    private String cookie(HttpServletRequest request, String name) {
        if (request.getCookies() == null) return null;
        for (Cookie candidate : request.getCookies()) if (name.equals(candidate.getName())) return candidate.getValue();
        return null;
    }
}
