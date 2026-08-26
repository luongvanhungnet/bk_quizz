package com.genquiz.bk.quiz;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class QuizLimitsTest {
    @Test
    void allowsOneHundredQuestionsPerQuiz() {
        assertEquals(100, QuizLimits.MAX_QUESTIONS_PER_QUIZ);
    }
}
