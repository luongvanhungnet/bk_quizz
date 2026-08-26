package com.genquiz.bk.quiz;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;

class QuizGenerationBatchPlannerTest {
    @Test
    void enforcesTwentyQuestionBatchLimitForBoundarySizes() {
        for (int total : List.of(1, 20, 21, 50, 100)) {
            var batches = QuizGenerationBatchPlanner.plan(
                    new QuizDtos.QuestionCounts(total, 0, 0),
                    CognitiveMode.L1, 20);

            assertEquals((total + 19) / 20, batches.size());
            assertEquals(total, batches.stream()
                    .mapToInt(QuizGenerationBatchPlanner.BatchPlan::size).sum());
            assertTrue(batches.stream().allMatch(batch -> batch.size() <= 20));
        }
    }

    @Test
    void plansBalancedQuizWithExactHamiltonDistribution() {
        var requested = new QuizDtos.QuestionCounts(4, 3, 3);

        List<QuizGenerationBatchPlanner.BatchPlan> batches =
                QuizGenerationBatchPlanner.plan(requested, CognitiveMode.BALANCED, 20);

        assertEquals(List.of(10),
                batches.stream().map(QuizGenerationBatchPlanner.BatchPlan::size).toList());
        assertEquals(4, batches.stream().mapToInt(batch -> batch.counts().singleChoice()).sum());
        assertEquals(3, batches.stream().mapToInt(batch -> batch.counts().multipleSelect()).sum());
        assertEquals(3, batches.stream().mapToInt(batch -> batch.counts().fillBlank()).sum());
        var levels = batches.stream().flatMap(batch -> batch.levels().stream()).toList();
        assertEquals(4, levels.stream().filter(level -> level == CognitiveLevel.L3).count());
        assertEquals(3, levels.stream().filter(level -> level == CognitiveLevel.L2).count());
        assertEquals(2, levels.stream().filter(level -> level == CognitiveLevel.L4).count());
        assertEquals(1, levels.stream().filter(level -> level == CognitiveLevel.L1).count());
        assertEquals(0, levels.stream().filter(level -> level == CognitiveLevel.L5).count());
    }

    @Test
    void distributesFortyQuestionsAsFourTenFourteenTenTwo() {
        var levels = QuizGenerationBatchPlanner.levels(CognitiveMode.BALANCED, 40);
        assertEquals(4, levels.stream().filter(level -> level == CognitiveLevel.L1).count());
        assertEquals(10, levels.stream().filter(level -> level == CognitiveLevel.L2).count());
        assertEquals(14, levels.stream().filter(level -> level == CognitiveLevel.L3).count());
        assertEquals(10, levels.stream().filter(level -> level == CognitiveLevel.L4).count());
        assertEquals(2, levels.stream().filter(level -> level == CognitiveLevel.L5).count());
    }
}
