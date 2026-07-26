package com.genquiz.bk.job;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
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
}
