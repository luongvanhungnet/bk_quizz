package com.genquiz.bk.attempt;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record DashboardActivityRow(
        UUID attemptId,
        UUID quizId,
        String quizTitle,
        AttemptStatus status,
        BigDecimal percentage,
        Instant occurredAt) {}
