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
}
