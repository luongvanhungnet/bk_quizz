package com.genquiz.bk.quiz;

import com.genquiz.bk.topic.Visibility;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public final class QuizDtos {
    private QuizDtos() {}

    public record SaveRequest(
            @NotNull(message = "Chủ đề là bắt buộc") UUID topicId,
            @NotBlank(message = "Tiêu đề không được để trống")
            @Size(max = 200, message = "Tiêu đề tối đa 200 ký tự") String title,
            @Size(max = 5000, message = "Mô tả tối đa 5000 ký tự") String description,
            @NotNull Difficulty difficulty,
            @Min(value = 1, message = "Thời lượng tối thiểu 1 phút")
            @Max(value = 300, message = "Thời lượng tối đa 300 phút") int durationMinutes,
            @NotNull Visibility visibility) {}

    public record QuestionCounts(
            @Min(0) @Max(50) int singleChoice,
            @Min(0) @Max(50) int multipleSelect,
            @Min(0) @Max(50) int fillBlank) {
        public int total() { return singleChoice + multipleSelect + fillBlank; }
    }

    public record GenerateRequest(
            @NotNull UUID topicId,
            @NotEmpty(message = "Cần chọn ít nhất một tài liệu")
            @Size(max = 10, message = "Chỉ được chọn tối đa 10 tài liệu") List<UUID> sourceIds,
            @NotBlank @Size(max = 200) String title,
            @NotNull Difficulty difficulty,
            @Min(1) @Max(300) int durationMinutes,
            @NotNull Visibility visibility,
            @NotNull @Valid QuestionCounts questionCounts) {}

    public record QuizResponse(
            UUID id,
            UUID topicId,
            UUID ownerId,
            String title,
            String description,
            QuizStatus status,
            Visibility visibility,
            GenerationMode generationMode,
            Difficulty difficulty,
            int durationMinutes,
            long questionCount,
            String errorCode,
            String errorMessage,
            Instant publishedAt,
            Instant createdAt,
            Instant updatedAt,
            long version) {
        public static QuizResponse from(Quiz quiz, long questionCount) {
            return new QuizResponse(quiz.getId(), quiz.getTopicId(), quiz.getOwnerId(), quiz.getTitle(),
                    quiz.getDescription(), quiz.getStatus(), quiz.getVisibility(), quiz.getGenerationMode(),
                    quiz.getDifficulty(), quiz.getDurationMinutes(), questionCount, quiz.getErrorCode(),
                    quiz.getErrorMessage(), quiz.getPublishedAt(), quiz.getCreatedAt(), quiz.getUpdatedAt(),
                    quiz.getVersion());
        }
    }

    public record GenerateResponse(QuizResponse quiz, UUID jobId) {}

    public record OptionRequest(
            @NotBlank(message = "Lựa chọn không được để trống") @Size(max = 2000) String text,
            boolean correct) {}

    public record QuestionRequest(
            @NotNull QuestionType type,
            @NotBlank(message = "Nội dung câu hỏi không được để trống") @Size(max = 10000) String prompt,
            @Size(max = 10000) String explanation,
            @NotNull @Min(0) BigDecimal points,
            @NotNull Difficulty difficulty,
            UUID sourceChunkId,
            List<@Valid OptionRequest> options,
            List<@NotBlank @Size(max = 2000) String> acceptedAnswers) {}

    public record OptionResponse(UUID id, String text, boolean correct, int position) {}

    public record CitationRequest(UUID sourceChunkId, CitationRole role, String evidenceQuote) {}
    public record GroundedQuestion(QuestionRequest question, List<CitationRequest> citations) {}
    public record CitationResponse(UUID sourceChunkId, UUID sourceDocumentId, String filename,
                                   Integer pageNumber, Integer slideNumber, int chunkIndex, String heading,
                                   CitationRole role, String evidenceQuote) {}

    /** Author/editor representation. Attempt endpoints deliberately use separate redacted DTOs. */
    public record QuestionResponse(
            UUID id,
            UUID quizId,
            QuestionType type,
            String prompt,
            String explanation,
            BigDecimal points,
            int position,
            Difficulty difficulty,
            UUID sourceChunkId,
            List<OptionResponse> options,
            List<String> acceptedAnswers,
            List<CitationResponse> citations,
            long version) {}

    public record ReorderRequest(@NotEmpty List<UUID> questionIds) {}
}
