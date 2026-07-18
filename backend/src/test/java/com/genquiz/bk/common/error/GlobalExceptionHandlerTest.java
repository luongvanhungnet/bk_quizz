package com.genquiz.bk.common.error;

import org.junit.jupiter.api.Test;
import org.springframework.dao.DataRetrievalFailureException;
import org.springframework.mock.web.MockHttpServletRequest;

import static org.assertj.core.api.Assertions.assertThat;

class GlobalExceptionHandlerTest {
    @Test
    void classroomJoinDatabaseFailureReturnsSpecificErrorAndTraceId() {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/classrooms/join");
        request.setAttribute("traceId", "join-trace-123");

        var response = new GlobalExceptionHandler().handleDataAccess(
                new DataRetrievalFailureException("database details must stay private"), request);

        assertThat(response.getStatusCode().value()).isEqualTo(503);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().errors().get(0).code()).isEqualTo("CLASSROOM_JOIN_DATABASE_ERROR");
        assertThat(response.getBody().traceId()).isEqualTo("join-trace-123");
        assertThat(response.getBody().message()).contains("tham gia lớp học");
        assertThat(response.getBody().message()).doesNotContain("database details");
    }
}
