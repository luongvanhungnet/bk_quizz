package com.genquiz.bk.job;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import com.genquiz.bk.auth.ResendConnectivityException;
import com.genquiz.bk.auth.ResendDeliveryException;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataIntegrityViolationException;

class JobWorkerFailureClassificationTest {
    @Test
    void quizGeminiRetryNeverRunsEarlierThanFiveMinutes() {
        Duration minimum = Duration.ofMinutes(5);

        assertEquals(minimum, JobWorker.retryDelay(
                JobType.QUIZ_GENERATION, Duration.ofSeconds(30), minimum));
        assertEquals(Duration.ofMinutes(8), JobWorker.retryDelay(
                JobType.QUIZ_GENERATION, Duration.ofMinutes(8), minimum));
    }

    @Test
    void quizConstraintFailureIsTerminalAndKeepsItsRealCause() {
        Exception failure = new DataIntegrityViolationException("ck_questions_difficulty");

        assertEquals("QUIZ_PERSISTENCE_FAILED",
                JobWorker.failureCode(JobType.QUIZ_GENERATION, failure));
        assertTrue(JobWorker.isPermanentFailure(JobType.QUIZ_GENERATION, failure));
    }

    @Test
    void authEmailKeepsSafeResendFailureCode() {
        Exception failure = new ResendDeliveryException(
                "RESEND_AUTHENTICATION_FAILED",
                "Khóa API Resend không hợp lệ hoặc đã bị thu hồi.");

        assertEquals("RESEND_AUTHENTICATION_FAILED",
                JobWorker.failureCode(JobType.AUTH_EMAIL, failure));
    }

    @Test
    void authEmailKeepsSafeResendConnectivityCode() {
        Exception failure = new ResendConnectivityException(
                "RESEND_CONNECTION_TIMEOUT",
                "Kết nối từ máy chủ tới Resend đã quá thời gian chờ.",
                Duration.ofSeconds(30), new java.net.http.HttpConnectTimeoutException("timeout"));

        assertEquals("RESEND_CONNECTION_TIMEOUT",
                JobWorker.failureCode(JobType.AUTH_EMAIL, failure));
    }
}
