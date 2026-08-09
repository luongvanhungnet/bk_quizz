package com.genquiz.bk.quiz;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class QuizGenerationDifficultyTest {
    @Test
    void assignsConcreteDifficultyWhenLegacyRagResponseOmitsIt() {
        assertEquals(Difficulty.MEDIUM,
                QuizGenerationHandler.resolveQuestionDifficulty(null, Difficulty.MIXED, 0, 1));
        assertEquals(Difficulty.EASY,
                QuizGenerationHandler.resolveQuestionDifficulty(null, Difficulty.MIXED, 0, 2));
        assertEquals(Difficulty.HARD,
                QuizGenerationHandler.resolveQuestionDifficulty(null, Difficulty.MIXED, 1, 2));
        assertEquals(Difficulty.MEDIUM,
                QuizGenerationHandler.resolveQuestionDifficulty("MEDIUM", Difficulty.MIXED, 0, 4));
    }


    @Test
    void distinguishesCognitiveRepairWaitingFromProviderRetry() {
        assertEquals(
                "WAITING_COGNITIVE_RETRY",
                QuizGenerationHandler.retryStage(
                        "COGNITIVE_CONSTRAINT_VIOLATION", true));
        assertEquals(
                "WAITING_GEMINI_RETRY",
                QuizGenerationHandler.retryStage("GEMINI_TIMEOUT", true));
        assertEquals(
                "WAITING_CITATION_RETRY",
                QuizGenerationHandler.retryStage("INVALID_CITATION_QUOTE", true));
        assertEquals(
                "WAITING_RAG_RETRY",
                QuizGenerationHandler.retryStage("RAG_TRANSIENT_ERROR", true));
        assertEquals(
                "WAITING_RAG_RETRY",
                QuizGenerationHandler.retryStage(
                        "RAG_STREAM_READ_TIMEOUT", true));
        assertEquals(
                "BATCH_FAILED",
                QuizGenerationHandler.retryStage("RAG_INTERNAL_ERROR", false));
        assertEquals(
                "BATCH_FAILED",
                QuizGenerationHandler.retryStage(
                        "COGNITIVE_CONSTRAINT_VIOLATION", false));
    }
}
