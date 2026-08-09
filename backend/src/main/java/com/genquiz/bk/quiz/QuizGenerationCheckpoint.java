package com.genquiz.bk.quiz;

import com.genquiz.bk.rag.RagDtos;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import tools.jackson.databind.JsonNode;

record QuizGenerationCheckpoint(
        int contractVersion,
        String fingerprint,
        List<BatchState> batches) {
    static final int CONTRACT_VERSION = 5;

    static QuizGenerationCheckpoint create(
            String fingerprint, List<QuizGenerationBatchPlanner.BatchPlan> plans) {
        return new QuizGenerationCheckpoint(
                CONTRACT_VERSION,
                fingerprint,
                plans.stream().map(plan -> new BatchState(
                        plan.index(),
                        new RagDtos.Counts(
                                plan.counts().singleChoice(),
                                plan.counts().multipleSelect(),
                                plan.counts().fillBlank()),
                        plan.levels().stream().map(Enum::name).toList(),
                        0, null, null, null, null, null)).toList());
    }

    boolean matches(String expectedFingerprint, int expectedBatchCount) {
        return contractVersion == CONTRACT_VERSION
                && fingerprint.equals(expectedFingerprint)
                && batches.size() == expectedBatchCount;
    }

    int nextIncompleteIndex() {
        for (int index = 0; index < batches.size(); index++) {
            if (batches.get(index).generated() == null) return index;
        }
        return -1;
    }

    QuizGenerationCheckpoint recordAttempt(int index) {
        BatchState current = batches.get(index);
        return replace(index, new BatchState(
                current.index(), current.counts(), current.difficultyPlan(),
                current.attempts() + 1, current.generated(), current.partialQuestions(),
                current.partialMetadata(), null, null));
    }

    QuizGenerationCheckpoint complete(int index, RagDtos.GeneratedQuiz generated) {
        BatchState current = batches.get(index);
        return replace(index, new BatchState(
                current.index(), current.counts(), current.difficultyPlan(),
                current.attempts(), generated, null, null, null, null));
    }

    QuizGenerationCheckpoint partial(int index, JsonNode checkpoint) {
        BatchState current = batches.get(index);
        boolean structured = checkpoint != null
                && checkpoint.isObject()
                && "STRUCTURED_OUTPUT_CHECKPOINT".equals(
                checkpoint.path("type").stringValue(""));
        JsonNode questions = structured
                ? checkpoint.path("acceptedQuestions").deepCopy()
                : checkpoint;
        JsonNode metadata = structured ? checkpoint.deepCopy() : current.partialMetadata();
        return replace(index, new BatchState(
                current.index(), current.counts(), current.difficultyPlan(),
                current.attempts(), current.generated(), questions, metadata, null, null));
    }

    QuizGenerationCheckpoint fail(int index, String code, String requestId) {
        BatchState current = batches.get(index);
        return replace(index, new BatchState(
                current.index(), current.counts(), current.difficultyPlan(),
                current.attempts(), current.generated(), current.partialQuestions(),
                current.partialMetadata(), code, requestId));
    }

    RagDtos.GeneratedQuiz restorePartialAccounting(
            int index, RagDtos.GeneratedQuiz generated) {
        JsonNode metadata = batches.get(index).partialMetadata();
        if (metadata == null || !metadata.isObject()) return generated;
        String model = generated.model();
        JsonNode checkpointModel = metadata.get("model");
        if ((model == null || "checkpoint".equals(model))
                && checkpointModel != null && checkpointModel.isString()) {
            model = checkpointModel.stringValue();
        }
        Map<String, Integer> usage = generated.usage();
        JsonNode checkpointUsage = metadata.get("usage");
        int generatedTokens = usage == null ? 0 : usage.getOrDefault("totalTokens", 0);
        if (generatedTokens == 0 && checkpointUsage != null && checkpointUsage.isObject()) {
            usage = Map.of(
                    "inputTokens", checkpointUsage.path("inputTokens").asInt(0),
                    "outputTokens", checkpointUsage.path("outputTokens").asInt(0),
                    "totalTokens", checkpointUsage.path("totalTokens").asInt(0));
        }
        return new RagDtos.GeneratedQuiz(
                generated.questions(), model, usage,
                generated.validationStatus(), generated.validationWarnings(),
                generated.requestedCount(), generated.savedCount(), generated.warningCount());
    }

    QuizGenerationCheckpoint resetIncompleteAttempts() {
        List<BatchState> reset = batches.stream().map(batch ->
                batch.generated() == null
                        ? new BatchState(batch.index(), batch.counts(),
                        batch.difficultyPlan(), 0, null, batch.partialQuestions(),
                        batch.partialMetadata(), null, null)
                        : batch).toList();
        return new QuizGenerationCheckpoint(contractVersion, fingerprint, reset);
    }

    List<RagDtos.GeneratedQuestion> generatedQuestions() {
        return batches.stream()
                .filter(batch -> batch.generated() != null)
                .flatMap(batch -> batch.generated().questions().stream())
                .toList();
    }

    List<String> excludedPrompts() {
        List<String> result = new ArrayList<>();
        for (RagDtos.GeneratedQuestion question : generatedQuestions()) {
            String prompt = question.prompt() == null ? "" : question.prompt().strip();
            result.add(prompt.substring(0, Math.min(500, prompt.length())));
        }
        return List.copyOf(result);
    }

    private QuizGenerationCheckpoint replace(int index, BatchState value) {
        List<BatchState> updated = new ArrayList<>(batches);
        updated.set(index, value);
        return new QuizGenerationCheckpoint(contractVersion, fingerprint, List.copyOf(updated));
    }

    record BatchState(
            int index,
            RagDtos.Counts counts,
            List<String> difficultyPlan,
            int attempts,
            RagDtos.GeneratedQuiz generated,
            JsonNode partialQuestions,
            JsonNode partialMetadata,
            String lastErrorCode,
            String upstreamRequestId) {
    }
}
