package com.genquiz.bk.quiz;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class QuestionValidationReviewTest {
    @Test
    void manualReviewPreservesWarningsWithoutPretendingTheyAreVerified() {
        Question question = new Question(
                UUID.randomUUID(), null, QuestionType.SINGLE_CHOICE,
                "Gram-Schmidt?", "Giải thích", BigDecimal.ONE, 0,
                Difficulty.MEDIUM);
        question.applyAiValidation(AiValidationStatus.WARNING, List.of(
                new QuizDtos.AiValidationWarning(
                        "INVALID_CITATION_QUOTE", "QUESTION", null, null,
                        "chunk-id", "Thiếu nguồn")));
        UUID reviewer = UUID.randomUUID();

        question.markValidationReviewed(reviewer, "Đã đối chiếu tài liệu", java.time.Instant.now());

        assertEquals(AiValidationStatus.REVIEWED, question.getAiValidationStatus());
        assertEquals(1, question.getValidationWarnings().size());
        assertEquals(reviewer, question.getValidationReviewedBy());
        assertNotNull(question.getValidationReviewedAt());

        question.undoValidationReview();
        assertEquals(AiValidationStatus.WARNING, question.getAiValidationStatus());
        assertEquals(1, question.getValidationWarnings().size());
    }
}
