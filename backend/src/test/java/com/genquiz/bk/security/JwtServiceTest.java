package com.genquiz.bk.security;

import com.genquiz.bk.config.AppProperties;
import com.genquiz.bk.user.Role;
import com.genquiz.bk.user.User;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class JwtServiceTest {
    private final AppProperties properties = new AppProperties(List.of("http://localhost:5173"),
            new AppProperties.Security("01234567890123456789012345678901", Duration.ofMinutes(15),
                    Duration.ofDays(7), "bkquiz_refresh", "XSRF-TOKEN", false, 12),
            new AppProperties.Storage("http://localhost:9000", "us-east-1", "key", "secret", "bucket", true),
            new AppProperties.Ai(false, "gemini-3.5-flash", "gemini-embedding-2", 768,
                    Duration.ofSeconds(60), 3, 50, 10, 100),
            new AppProperties.Jobs(false, Duration.ofSeconds(1), Duration.ofMinutes(2), 5));

    @Test
    void accessTokenChuaSubjectVaRole() {
        User user = new User("Sinh viên BK", "student@example.com", "hashed-password-value-value");
        user.setRole(Role.STUDENT);
        JwtService service = new JwtService(properties);
        JwtService.AccessClaims claims = service.verifyAccessToken(service.issueAccessToken(user));
        assertThat(claims.userId()).isEqualTo(user.getId());
        assertThat(claims.role()).isEqualTo(Role.STUDENT);
        assertThat(claims.email()).isEqualTo("student@example.com");
    }

    @Test
    void tuChoiTokenBiSua() {
        User user = new User("Sinh viên BK", "student@example.com", "hashed-password-value-value");
        JwtService service = new JwtService(properties);
        String token = service.issueAccessToken(user);
        assertThatThrownBy(() -> service.verifyAccessToken(token.substring(0, token.length() - 2) + "xx"))
                .isInstanceOf(JwtService.JwtValidationException.class);
    }
}
