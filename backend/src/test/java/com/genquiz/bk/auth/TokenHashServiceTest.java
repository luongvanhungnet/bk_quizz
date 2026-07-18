package com.genquiz.bk.auth;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class TokenHashServiceTest {
    private final TokenHashService service = new TokenHashService();

    @Test
    void taoSecretNgauNhienVaSoSanhHashTheoConstantTime() {
        String first = service.newSecret();
        String second = service.newSecret();
        assertThat(first).isNotBlank().isNotEqualTo(second);
        assertThat(service.matches(first, service.hash(first))).isTrue();
        assertThat(service.matches(second, service.hash(first))).isFalse();
    }
}

