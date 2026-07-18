package com.genquiz.bk.attempt;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class AttemptReleasePolicyTest {

    @Test
    void afterDueDateDoesNotReleaseAnswerKeyEarly() {
        Instant start = Instant.parse("2026-07-11T00:00:00Z");
        Instant due = start.plus(1, ChronoUnit.DAYS);
        Attempt attempt = new Attempt(UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(), 1, 1,
                start, start.plus(30, ChronoUnit.MINUTES), AnswerReleasePolicy.AFTER_DUE_DATE, due);
        attempt.submit(BigDecimal.ONE, BigDecimal.ONE, 1, "submit-1", start.plus(10, ChronoUnit.MINUTES));

        assertFalse(attempt.answersMayBeReleased(due.minusSeconds(1)));
        assertTrue(attempt.answersMayBeReleased(due));
    }

    @Test
    void neverPolicyNeverReleasesAnswerKey() {
        Instant start = Instant.parse("2026-07-11T00:00:00Z");
        Attempt attempt = new Attempt(UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(), 1, 1,
                start, start.plus(30, ChronoUnit.MINUTES), AnswerReleasePolicy.NEVER, start.plusSeconds(60));
        attempt.submit(BigDecimal.ZERO, BigDecimal.ONE, 0, "submit-2", start.plusSeconds(30));

        assertFalse(attempt.answersMayBeReleased(start.plus(365, ChronoUnit.DAYS)));
    }
}
