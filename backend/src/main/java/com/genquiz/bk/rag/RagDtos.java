package com.genquiz.bk.rag;

import java.util.List;
import java.util.Map;
import java.util.UUID;

public final class RagDtos {
    private RagDtos() {}
    public record Upload(UUID documentId, UUID jobId, String documentStatus, String jobStatus) {}
    public record Health(String status, Map<String, String> checks, int queueLength,
                         int pendingJobs, int runningJobs, long oldestPendingSeconds) {}
    public record IndexJob(UUID id, UUID documentId, String status, int progress, String step,
                           int attempts, int maxAttempts, String errorCode, String errorMessage) {}
    public record Document(UUID id, String filename, String mimeType, long size, String status,
                           Integer pageCount, int chunkCount, String error, String indexedAt) {}
    public record Chunk(UUID chunkId, UUID documentId, String filename, Integer pageNumber,
                        Integer slideNumber, int chunkIndex, String heading, String text) {}
    public record Pagination(int page, int size, long totalItems, int totalPages) {}
    public record Chunks(List<Chunk> items, Pagination pagination) {}
    public record Counts(int singleChoice, int multipleSelect, int fillBlank) {}
    public record GenerateRequest(List<UUID> documentIds, String title, String difficulty,
                                  Counts questionCounts, int batchIndex, int totalBatches,
                                  List<String> difficultyPlan, List<String> excludedPrompts) {
        public GenerateRequest(
                List<UUID> documentIds,
                String title,
                String difficulty,
                Counts questionCounts) {
            this(documentIds, title, difficulty, questionCounts,
                    0, 1, null, List.of());
        }
    }
    public record Option(String text, boolean correct) {}
    public record Citation(UUID chunkId, UUID documentId, String filename, Integer pageNumber,
                           Integer slideNumber, int chunkIndex, String heading, String evidenceQuote) {}
    public record GeneratedQuestion(String type, String difficulty, String prompt, String explanation, List<Option> options,
                                    List<String> acceptedAnswers, List<Citation> questionCitations,
                                    List<Citation> answerCitations, List<Citation> explanationCitations) {}
    public record GeneratedQuiz(List<GeneratedQuestion> questions, String model, java.util.Map<String, Integer> usage) {}
}
