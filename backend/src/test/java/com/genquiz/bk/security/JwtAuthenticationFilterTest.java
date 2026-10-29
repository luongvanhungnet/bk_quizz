package com.genquiz.bk.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.genquiz.bk.user.Role;
import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserRepository;
import jakarta.servlet.FilterChain;
import java.util.Optional;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.context.SecurityContextHolder;

class JwtAuthenticationFilterTest {
    @AfterEach
    void clearContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void authoritiesAreReloadedFromDatabaseInsteadOfTrustedFromToken() throws Exception {
        JwtService jwt = mock(JwtService.class);
        UserRepository users = mock(UserRepository.class);
        AuthorizationService authorization = mock(AuthorizationService.class);
        User user = new User("Admin", "admin@example.com", "hash-value-long-enough");
        when(jwt.verifyAccessToken("signed-token")).thenReturn(new JwtService.AccessClaims(
                user.getId(), Role.STUDENT, user.getEmail(), Set.of("USER"), Set.of()));
        when(users.findById(user.getId())).thenReturn(Optional.of(user));
        when(authorization.snapshot(user.getId())).thenReturn(
                new AuthorizationService.AuthorizationSnapshot(
                        Set.of("USER", "OWNER"), Set.of("admin:grant", "admin:revoke")));
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("Authorization", "Bearer signed-token");
        FilterChain chain = mock(FilterChain.class);
        MockHttpServletResponse response = new MockHttpServletResponse();

        new JwtAuthenticationFilter(jwt, users, authorization)
                .doFilterInternal(request, response, chain);

        assertThat(SecurityContextHolder.getContext().getAuthentication().getAuthorities())
                .extracting("authority")
                .contains("ROLE_OWNER", "admin:grant", "admin:revoke")
                .doesNotContain("ROLE_ADMIN");
        verify(chain).doFilter(request, response);
    }
}
