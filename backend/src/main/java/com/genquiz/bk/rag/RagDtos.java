package com.genquiz.bk.rag;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import tools.jackson.databind.JsonNode;

public final class RagDtos {
    public static final String QUIZ_GENERATION_CONTRACT = "cognitive-repair-v1";
    private RagDtos() {}
    public record Upload(UUID documentId, UUID jobId, String documentStatus, String jobStatus) {}
    public record Health(String status, Map<String, String> checks, int queueLength,
                         int pendingJobs, int runningJobs, long oldestPendingSeconds) {}
    public record Capabilities(String quizGenerationContract,
                               Map<String, Boolean> capabilities,
                               String buildRevision) {}
    public record IndexJob(UUID id, UUID documentId, String status, int progress, String step,
                           int attempts, int maxAttempts, String errorCode, String errorMessage) {}
    public record Document(UUID id, String filename, String mimeType, long size, String status,
                           Integer pageCount, int chunkCount, String error, String indexedAt,
                           String mathExtractionStatus, int mathFormulaCount, int mathWarningCount) {}
    public record Chunk(UUID chunkId, UUID documentId, String filename, Integer pageNumber,
                        Integer slideNumber, int chunkIndex, String heading, String text,
                        String rawText, boolean mathEnhanced) {}
    public record Pagination(int page, int size, long totalItems, int totalPages) {}
    public record Chunks(List<Chunk> items, Pagination pagination) {}
    public record Counts(int singleChoice, int multipleSelect, int fillBlank) {}
    public record CognitiveConstraint(String cognitiveLevel, int conceptMin, int conceptMax,
                                      int reasoningMin, int reasoningMax, boolean requiresNovelScenario,
                                      boolean answerDirectlyPresent, boolean requiresComparison,
                                      int scoreMin, Integer scoreMax) {}
    public record QuestionPlan(String planSlotId, String questionType,
                               String cognitiveLevel, CognitiveConstraint constraint) {}
    public record GenerateRequest(List<UUID> documentIds, String title, String difficulty,
                                  String cognitiveMode,
                                  Counts questionCounts, int batchIndex, int totalBatches,
                                  List<String> difficultyPlan, List<QuestionPlan> questionPlan,
                                  List<String> excludedPrompts, JsonNode acceptedQuestions) {
        public GenerateRequest(List<UUID> documentIds, String title, String difficulty,
                               String cognitiveMode, Counts questionCounts,
                               int batchIndex, int totalBatches,
                               List<String> difficultyPlan, List<QuestionPlan> questionPlan,
                               List<String> excludedPrompts) {
            this(documentIds, title, difficulty, cognitiveMode, questionCounts,
                    batchIndex, totalBatches, difficultyPlan, questionPlan,
                    excludedPrompts, null);
        }
        public GenerateRequest(List<UUID> documentIds, String title, String difficulty,
                               Counts questionCounts, int batchIndex, int totalBatches,
                               List<String> difficultyPlan, List<String> excludedPrompts) {
            this(documentIds, title, difficulty, null, questionCounts, batchIndex, totalBatches,
                    difficultyPlan, null, excludedPrompts, null);
        }
        public GenerateRequest(
                List<UUID> documentIds,
                String title,
                String difficulty,
                Counts questionCounts) {
            this(documentIds, title, difficulty, null, questionCounts,
                    0, 1, null, null, List.of(), null);
        }
    }
    public record Option(String text, boolean correct) {}
    public record Citation(UUID chunkId, UUID documentId, String filename, Integer pageNumber,
                           Integer slideNumber, int chunkIndex, String heading, String evidenceQuote,
                           String chunkText, String rawText, boolean mathEnhanced,
                           String snapshotFingerprint) {
        public Citation(UUID chunkId, UUID documentId, String filename, Integer pageNumber,
                        Integer slideNumber, int chunkIndex, String heading, String evidenceQuote) {
            this(chunkId, documentId, filename, pageNumber, slideNumber, chunkIndex,
                    heading, evidenceQuote, null, null, false, null);
        }
    }
    public record ComplexityProfile(int conceptCount, int reasoningStepCount,
                                    boolean requiresNovelScenario, boolean answerDirectlyPresent,
                                    boolean requiresComparison, List<String> conceptsUsed,
                                    String novelScenarioSummary, int complexityScore) {}
    public record GeneratedQuestion(String type, String difficulty, String planSlotId,
                                    String cognitiveLevel, ComplexityProfile complexityProfile,
                                    String prompt, String explanation, List<Option> options,
                                    List<String> acceptedAnswers, List<Citation> questionCitations,
                                    List<Citation> answerCitations, List<Citation> explanationCitations,
                                    String validationStatus,
                                    List<QuizValidationWarning> validationWarnings,
                                    boolean complexityVerified) {
        public GeneratedQuestion(String type, String difficulty, String planSlotId,
                                 String cognitiveLevel, ComplexityProfile complexityProfile,
                                 String prompt, String explanation, List<Option> options,
                                 List<String> acceptedAnswers, List<Citation> questionCitations,
                                 List<Citation> answerCitations,
                                 List<Citation> explanationCitations) {
            this(type, difficulty, planSlotId, cognitiveLevel, complexityProfile,
                    prompt, explanation, options, acceptedAnswers, questionCitations,
                    answerCitations, explanationCitations, "VERIFIED", List.of(), true);
        }
        public GeneratedQuestion(String type, String difficulty, String prompt, String explanation,
                                 List<Option> options, List<String> acceptedAnswers,
                                 List<Citation> questionCitations, List<Citation> answerCitations,
                                 List<Citation> explanationCitations) {
            this(type, difficulty, null, null, null, prompt, explanation, options, acceptedAnswers,
                    questionCitations, answerCitations, explanationCitations,
                    "VERIFIED", List.of(), true);
        }
    }
    public record QuizValidationWarning(String code, String role, Object expected,
                                        Object actual, String sourceId, String message) {}
    public record GeneratedQuiz(List<GeneratedQuestion> questions, String model,
                                java.util.Map<String, Integer> usage,
                                String validationStatus,
                                List<QuizValidationWarning> validationWarnings,
                                Integer requestedCount, Integer savedCount, Integer warningCount) {
        public GeneratedQuiz(List<GeneratedQuestion> questions, String model,
                             java.util.Map<String, Integer> usage) {
            this(questions, model, usage, "VERIFIED", List.of(),
                    questions == null ? 0 : questions.size(),
                    questions == null ? 0 : questions.size(), 0);
        }
    }
}
