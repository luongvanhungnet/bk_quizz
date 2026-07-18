package com.genquiz.bk.attempt;

import java.time.Instant;
import java.util.UUID;

/** Boundary implemented by the classroom module, avoiding a domain dependency cycle. */
public interface AssignmentPolicyGateway {
    Policy authorizeStart(UUID assignmentId, UUID quizId, UUID userId, Instant now);

    record Policy(Instant opensAt, Instant dueAt, int durationMinutes, int maxAttempts,
                  AnswerReleasePolicy answerReleasePolicy, boolean showScore, boolean allowReview,
                  boolean shuffleQuestions, boolean shuffleOptions) {}
}
