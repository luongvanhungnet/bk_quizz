package com.genquiz.bk.quiz;

import java.util.ArrayList;
import java.util.List;

public final class QuizGenerationBatchPlanner {
    private static final CognitiveLevel[] BALANCED_ORDER = {
            CognitiveLevel.L3, CognitiveLevel.L2, CognitiveLevel.L4,
            CognitiveLevel.L1, CognitiveLevel.L5
    };
    private static final double[] BALANCED_WEIGHTS = {0.35, 0.25, 0.25, 0.10, 0.05};

    private QuizGenerationBatchPlanner() {}

    public static List<BatchPlan> plan(
            QuizDtos.QuestionCounts requested, CognitiveMode mode, int maxBatchSize) {
        if (maxBatchSize < 1 || maxBatchSize > 20) {
            throw new IllegalArgumentException("Quiz batch size phải từ 1 đến 20.");
        }
        int[] remaining = {
                requested.singleChoice(), requested.multipleSelect(), requested.fillBlank()
        };
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

        List<CognitiveLevel> levels = levels(mode, requested.total());
        List<BatchPlan> result = new ArrayList<>(countPlans.size());
        int offset = 0;
        for (int index = 0; index < countPlans.size(); index++) {
            QuizDtos.QuestionCounts counts = countPlans.get(index);
            var batchLevels = List.copyOf(levels.subList(offset, offset + counts.total()));
            result.add(new BatchPlan(index, countPlans.size(), counts, batchLevels));
            offset += counts.total();
        }
        return List.copyOf(result);
    }

    @Deprecated
    public static List<BatchPlan> plan(
            QuizDtos.QuestionCounts requested, Difficulty difficulty, int maxBatchSize) {
        return plan(requested, switch (difficulty) {
            case EASY -> CognitiveMode.L1;
            case MEDIUM -> CognitiveMode.L3;
            case HARD -> CognitiveMode.L5;
            case MIXED -> CognitiveMode.BALANCED;
        }, maxBatchSize);
    }

    static List<CognitiveLevel> levels(CognitiveMode mode, int total) {
        if (mode != CognitiveMode.BALANCED) {
            return java.util.Collections.nCopies(total, mode.fixedLevel());
        }
        int[] counts = new int[BALANCED_WEIGHTS.length];
        int assigned = 0;
        for (int i = 0; i < counts.length; i++) {
            counts[i] = (int) Math.floor(total * BALANCED_WEIGHTS[i]);
            assigned += counts[i];
        }
        List<Integer> remainderOrder = java.util.stream.IntStream.range(0, counts.length)
                .boxed().sorted((left, right) -> {
                    double leftRemainder = total * BALANCED_WEIGHTS[left] - counts[left];
                    double rightRemainder = total * BALANCED_WEIGHTS[right] - counts[right];
                    int compared = Double.compare(rightRemainder, leftRemainder);
                    return compared != 0 ? compared : Integer.compare(left, right);
                }).toList();
        for (int i = 0; i < total - assigned; i++) counts[remainderOrder.get(i)]++;

        List<CognitiveLevel> result = new ArrayList<>(total);
        int[] emitted = new int[counts.length];
        while (result.size() < total) {
            int selected = -1;
            double largestDeficit = Double.NEGATIVE_INFINITY;
            for (int i = 0; i < counts.length; i++) {
                if (emitted[i] >= counts[i]) continue;
                double deficit = (result.size() + 1.0) * counts[i] / total - emitted[i];
                if (deficit > largestDeficit) {
                    largestDeficit = deficit;
                    selected = i;
                }
            }
            emitted[selected]++;
            result.add(BALANCED_ORDER[selected]);
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

    public record BatchPlan(
            int index,
            int totalBatches,
            QuizDtos.QuestionCounts counts,
            List<CognitiveLevel> levels) {
        public int size() { return counts.total(); }

        @Deprecated
        public List<Difficulty> difficulties() {
            return levels.stream().map(level -> switch (level) {
                case L1 -> Difficulty.EASY;
                case L2, L3 -> Difficulty.MEDIUM;
                case L4, L5 -> Difficulty.HARD;
            }).toList();
        }
    }
}
