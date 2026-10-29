package com.genquiz.bk.security;

import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserRepository;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.stream.Collectors;

@Component
public class JwtAuthenticationFilter extends OncePerRequestFilter {
    private final JwtService jwt;
    private final UserRepository users;
    private final AuthorizationService authorization;

    public JwtAuthenticationFilter(JwtService jwt, UserRepository users, AuthorizationService authorization) {
        this.jwt = jwt;
        this.users = users;
        this.authorization = authorization;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        String header = request.getHeader("Authorization");
        if (header != null && header.startsWith("Bearer ")) {
            try {
                JwtService.AccessClaims claims = jwt.verifyAccessToken(header.substring(7).trim());
                User user = users.findById(claims.userId()).orElse(null);
                if (user != null && user.isActive() && user.getDeletedAt() == null) {
                    AuthorizationService.AuthorizationSnapshot snapshot = authorization.snapshot(user.getId());
                    UsernamePasswordAuthenticationToken authentication = new UsernamePasswordAuthenticationToken(
                            user.getId().toString(), null,
                            snapshot.authorities().stream()
                                    .map(SimpleGrantedAuthority::new)
                                    .collect(Collectors.toUnmodifiableSet()));
                    SecurityContextHolder.getContext().setAuthentication(authentication);
                }
            } catch (JwtService.JwtValidationException ignored) {
                SecurityContextHolder.clearContext();
            }
        }
        chain.doFilter(request, response);
    }
}
