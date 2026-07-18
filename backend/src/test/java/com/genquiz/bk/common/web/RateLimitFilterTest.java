package com.genquiz.bk.common.web;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import tools.jackson.databind.ObjectMapper;

class RateLimitFilterTest {
    @Test
    void limitsVerificationResendToThreeRequestsPerWindow() throws Exception {
        RateLimitFilter filter = new RateLimitFilter(new ObjectMapper());

        for (int attempt = 1; attempt <= 4; attempt++) {
            MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/auth/verify-email/resend");
            request.setRemoteAddr("203.0.113.10");
            MockHttpServletResponse response = new MockHttpServletResponse();
            filter.doFilter(request, response, (ignoredRequest, ignoredResponse) -> { });
            assertThat(response.getStatus()).isEqualTo(attempt <= 3 ? 200 : 429);
        }
    }

    @Test
    void trafficOnOneGeneralEndpointDoesNotBlockAnotherEndpoint() throws Exception {
        RateLimitFilter filter = new RateLimitFilter(new ObjectMapper());

        for (int attempt = 1; attempt <= 301; attempt++) {
            MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/quizzes");
            request.setRemoteAddr("203.0.113.20");
            MockHttpServletResponse response = new MockHttpServletResponse();
            filter.doFilter(request, response, (ignoredRequest, ignoredResponse) -> { });
        }

        MockHttpServletRequest topics = new MockHttpServletRequest("GET", "/api/topics");
        topics.setRemoteAddr("203.0.113.20");
        MockHttpServletResponse response = new MockHttpServletResponse();
        filter.doFilter(topics, response, (ignoredRequest, ignoredResponse) -> { });

        assertThat(response.getStatus()).isEqualTo(200);
        assertThat(response.getHeader("X-RateLimit-Remaining")).isEqualTo("299");
    }
}
