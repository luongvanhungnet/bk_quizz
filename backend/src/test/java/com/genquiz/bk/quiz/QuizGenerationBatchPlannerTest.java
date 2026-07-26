package com.genquiz.bk.quiz;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;

class QuizGenerationBatchPlannerTest {
    @Test
    void enforcesFourQuestionBatchLimitForBoundarySizes() {
        for (int total : List.of(1, 4, 5, 50)) {
            var batches = QuizGenerationBatchPlanner.plan(
                    new QuizDtos.QuestionCounts(total, 0, 0),
                    Difficulty.EASY, 4);

            assertEquals((total + 3) / 4, batches.size());
            assertEquals(total, batches.stream()
                    .mapToInt(QuizGenerationBatchPlanner.BatchPlan::size).sum());
            assertTrue(batches.stream().allMatch(batch -> batch.size() <= 4));
        }
    }

    @Test
    void plansTenQuestionsAsFourFourTwoWithoutChangingRequestedCounts() {
        var requested = new QuizDtos.QuestionCounts(4, 3, 3);

        List<QuizGenerationBatchPlanner.BatchPlan> batches =
                QuizGenerationBatchPlanner.plan(requested, Difficulty.MIXED, 4);

        assertEquals(List.of(4, 4, 2),
                batches.stream().map(QuizGenerationBatchPlanner.BatchPlan::size).toList());
        assertTrue(batches.stream().allMatch(batch -> batch.size() <= 4));
        assertEquals(4, batches.stream().mapToInt(batch -> batch.counts().singleChoice()).sum());
        assertEquals(3, batches.stream().mapToInt(batch -> batch.counts().multipleSelect()).sum());
        assertEquals(3, batches.stream().mapToInt(batch -> batch.counts().fillBlank()).sum());
        assertEquals(
                List.of(Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD,
                        Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD,
                        Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD,
                        Difficulty.EASY),
                batches.stream().flatMap(batch -> batch.difficulties().stream()).toList());
    }
}
