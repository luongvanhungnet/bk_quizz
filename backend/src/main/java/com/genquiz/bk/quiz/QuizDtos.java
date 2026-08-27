package com.genquiz.bk.quiz;

import com.genquiz.bk.topic.Visibility;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public final class QuizDtos {
    private QuizDtos() {}

    public record SaveRequest(
            @NotNull UUID topicId, @NotBlank @Size(max = 200) String title,
            @Size(max = 5000) String description, Difficulty difficulty,
            CognitiveMode cognitiveMode, @Min(1) @Max(300) int durationMinutes,
            @NotNull Visibility visibility) {
        public CognitiveMode resolvedCognitiveMode() {
            return cognitiveMode != null ? cognitiveMode : legacyMode(difficulty);
        }
    }

    public record QuestionCounts(
            @Min(0) @Max(QuizLimits.MAX_QUESTIONS_PER_QUIZ) int singleChoice,
            @Min(0) @Max(QuizLimits.MAX_QUESTIONS_PER_QUIZ) int multipleSelect,
            @Min(0) @Max(QuizLimits.MAX_QUESTIONS_PER_QUIZ) int fillBlank) {
        public int total() { return singleChoice + multipleSelect + fillBlank; }
    }

    public record GenerateRequest(
            @NotNull UUID topicId,
            @NotEmpty @Size(max = 10) List<UUID> sourceIds,
            @NotBlank @Size(max = 200) String title,
            Difficulty difficulty,
            CognitiveMode cognitiveMode,
            @Min(1) @Max(300) int durationMinutes,
            @NotNull Visibility visibility,
            @NotNull @Valid QuestionCounts questionCounts) {
        public CognitiveMode resolvedCognitiveMode() {
            return cognitiveMode != null ? cognitiveMode : legacyMode(difficulty);
        }
    }

    public record QuizResponse(
            UUID id, UUID topicId, UUID ownerId, String title, String description,
            QuizStatus status, Visibility visibility, GenerationMode generationMode,
            Difficulty difficulty, CognitiveMode cognitiveMode, int durationMinutes,
            long questionCount, String errorCode, String errorMessage,
            AiValidationStatus aiValidationStatus,
            List<AiValidationWarning> aiValidationWarnings,
            Instant publishedAt, Instant createdAt, Instant updatedAt, long version) {
        public static QuizResponse from(Quiz quiz, long questionCount) {
            return response(quiz, questionCount, false);
        }
        public static QuizResponse forOwner(Quiz quiz, long questionCount) {
            return response(quiz, questionCount, true);
        }
        private static QuizResponse response(Quiz quiz, long questionCount,
                                             boolean includeWarnings) {
            return new QuizResponse(quiz.getId(), quiz.getTopicId(), quiz.getOwnerId(), quiz.getTitle(),
                    quiz.getDescription(), quiz.getStatus(), quiz.getVisibility(), quiz.getGenerationMode(),
                    quiz.getDifficulty(), quiz.getCognitiveMode(), quiz.getDurationMinutes(), questionCount,
                    quiz.getErrorCode(), quiz.getErrorMessage(),
                    includeWarnings ? quiz.getAiValidationStatus() : null,
                    includeWarnings ? quiz.getAiValidationWarnings() : List.of(),
                    quiz.getPublishedAt(), quiz.getCreatedAt(),
                    quiz.getUpdatedAt(), quiz.getVersion());
        }
    }

    public record GenerateResponse(QuizResponse quiz, UUID jobId) {}
    public record QuestionImportResponse(int importedCount, long totalQuestionCount) {}
    public record AppendGenerateRequest(
            @NotEmpty @Size(max = 10) List<UUID> sourceIds,
            @NotNull CognitiveMode cognitiveMode,
            @NotNull @Valid QuestionCounts questionCounts) {}
    public record OptionRequest(@NotBlank @Size(max = 2000) String text, boolean correct) {}

    public record QuestionRequest(
            @NotNull QuestionType type, @NotBlank @Size(max = 10000) String prompt,
            @Size(max = 10000) String explanation, @NotNull @Min(0) BigDecimal points,
            Difficulty difficulty, CognitiveLevel cognitiveLevel, CognitiveProfile complexityProfile,
            UUID sourceChunkId, List<@Valid OptionRequest> options,
            List<@NotBlank @Size(max = 2000) String> acceptedAnswers) {
        public QuestionRequest(QuestionType type, String prompt, String explanation, BigDecimal points,
                               Difficulty difficulty, UUID sourceChunkId, List<OptionRequest> options,
                               List<String> acceptedAnswers) {
            this(type, prompt, explanation, points, difficulty, null, null,
                    sourceChunkId, options, acceptedAnswers);
        }
        public CognitiveLevel resolvedCognitiveLevel() {
            if (cognitiveLevel != null) return cognitiveLevel;
            return switch (difficulty == null ? Difficulty.MEDIUM : difficulty) {
                case EASY -> CognitiveLevel.L1;
                case MEDIUM, MIXED -> CognitiveLevel.L3;
                case HARD -> CognitiveLevel.L5;
            };
        }
    }

    public record OptionResponse(UUID id, String text, boolean correct, int position) {}
    public record CitationRequest(UUID sourceChunkId, CitationRole role, String evidenceQuote,
                                  UUID ragDocumentId, int chunkIndex, Integer pageNumber,
                                  Integer slideNumber, String heading, String chunkText,
                                  String rawText, boolean mathEnhanced,
                                  String snapshotFingerprint) {
        public CitationRequest(UUID sourceChunkId, CitationRole role, String evidenceQuote) {
            this(sourceChunkId, role, evidenceQuote, null, 0, null, null,
                    null, null, null, false, null);
        }
    }
    public record AiValidationWarning(String code, String role, Object expected,
                                      Object actual, String sourceId, String message) {}
    public record GroundedQuestion(QuestionRequest question, List<CitationRequest> citations,
                                   AiValidationStatus validationStatus,
                                   List<AiValidationWarning> validationWarnings) {
        public GroundedQuestion(QuestionRequest question, List<CitationRequest> citations) {
            this(question, citations, AiValidationStatus.VERIFIED, List.of());
        }
    }
    public record CitationResponse(UUID sourceChunkId, UUID sourceDocumentId, String filename,
                                   Integer pageNumber, Integer slideNumber, int chunkIndex, String heading,
                                   CitationRole role, String evidenceQuote) {}

    public record QuestionResponse(
            UUID id, UUID quizId, QuestionType type, String prompt, String explanation,
            BigDecimal points, int position, Difficulty difficulty, CognitiveLevel cognitiveLevel,
            CognitiveProfile complexityProfile, Integer complexityScore, UUID sourceChunkId,
            List<OptionResponse> options, List<String> acceptedAnswers,
            List<CitationResponse> citations, AiValidationStatus validationStatus,
            List<AiValidationWarning> validationWarnings, Instant validationReviewedAt,
            UUID validationReviewedBy, String validationReviewNote, long version) {}

    public record ValidationReviewRequest(@Size(max = 500) String note) {}

    public record ReorderRequest(@NotEmpty List<UUID> questionIds) {}

    private static CognitiveMode legacyMode(Difficulty difficulty) {
        if (difficulty == null) return CognitiveMode.BALANCED;
        return switch (difficulty) {
            case EASY -> CognitiveMode.L1;
            case MEDIUM -> CognitiveMode.L3;
            case HARD -> CognitiveMode.L5;
            case MIXED -> CognitiveMode.BALANCED;
        };
    }
}
