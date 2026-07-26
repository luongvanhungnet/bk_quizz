package com.genquiz.bk.quiz;

import java.util.ArrayList;
import java.util.List;

public final class QuizGenerationBatchPlanner {
    private QuizGenerationBatchPlanner() {}

    public static List<BatchPlan> plan(
            QuizDtos.QuestionCounts requested, Difficulty quizDifficulty, int maxBatchSize) {
        if (maxBatchSize < 1 || maxBatchSize > 4) {
            throw new IllegalArgumentException("Quiz batch size phải từ 1 đến 4.");
        }
        int[] remaining = {
                requested.singleChoice(),
                requested.multipleSelect(),
                requested.fillBlank()
        };
        int totalQuestions = requested.total();
        List<QuizDtos.QuestionCounts> countPlans = new ArrayList<>();
        int typeCursor = 0;
        while (remaining[0] + remaining[1] + remaining[2] > 0) {
            int[] current = new int[3];
            int size = 0;
            while (size < maxBatchSize && remaining[0] + remaining[1] + remaining[2] > 0) {
                int selected = nextAvailableType(remaining, typeCursor);
                current[selected]++;
                remaining[selected]--;
                size++;
                typeCursor = (selected + 1) % 3;
            }
            countPlans.add(new QuizDtos.QuestionCounts(current[0], current[1], current[2]));
        }

        List<Difficulty> globalDifficulties = difficulties(quizDifficulty, totalQuestions);
        List<BatchPlan> result = new ArrayList<>(countPlans.size());
        int offset = 0;
        for (int index = 0; index < countPlans.size(); index++) {
            QuizDtos.QuestionCounts counts = countPlans.get(index);
            List<Difficulty> batchDifficulties = List.copyOf(
                    globalDifficulties.subList(offset, offset + counts.total()));
            result.add(new BatchPlan(index, countPlans.size(), counts, batchDifficulties));
            offset += counts.total();
        }
        return List.copyOf(result);
    }

    private static int nextAvailableType(int[] remaining, int start) {
        for (int offset = 0; offset < remaining.length; offset++) {
            int candidate = (start + offset) % remaining.length;
            if (remaining[candidate] > 0) return candidate;
        }
        throw new IllegalStateException("Không còn loại câu hỏi để phân batch.");
    }

    private static List<Difficulty> difficulties(Difficulty quizDifficulty, int total) {
        if (quizDifficulty != Difficulty.MIXED) {
            return java.util.Collections.nCopies(total, quizDifficulty);
        }
        if (total == 1) return List.of(Difficulty.MEDIUM);
        if (total == 2) return List.of(Difficulty.EASY, Difficulty.HARD);
        Difficulty[] cycle = {Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD};
        return java.util.stream.IntStream.range(0, total)
                .mapToObj(index -> cycle[index % cycle.length]).toList();
    }

    public record BatchPlan(
            int index,
            int totalBatches,
            QuizDtos.QuestionCounts counts,
            List<Difficulty> difficulties) {
        public int size() {
            return counts.total();
        }
    }
}
