package com.genquiz.bk.quiz;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import java.util.ArrayList;
import java.util.List;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "questions")
public class Question {
    @Id
    private UUID id;

    @Column(name = "quiz_id", nullable = false, updatable = false)
    private UUID quizId;

    @Column(name = "source_chunk_id")
    private UUID sourceChunkId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 30)
    private QuestionType type;

    @Column(nullable = false, columnDefinition = "text")
    private String prompt;

    @Column(columnDefinition = "text")
    private String explanation;

    @Column(nullable = false, precision = 8, scale = 2)
    private BigDecimal points;

    @Column(nullable = false)
    private int position;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private Difficulty difficulty;

    @Enumerated(EnumType.STRING)
    @Column(name = "cognitive_level", nullable = false, length = 10)
    private CognitiveLevel cognitiveLevel;
    @Column(name = "concept_count") private Integer conceptCount;
    @Column(name = "reasoning_step_count") private Integer reasoningStepCount;
    @Column(name = "requires_novel_scenario") private Boolean requiresNovelScenario;
    @Column(name = "answer_directly_present") private Boolean answerDirectlyPresent;
    @Column(name = "requires_comparison") private Boolean requiresComparison;
    @Column(name = "complexity_verified", nullable = false) private boolean complexityVerified;
    @Column(name = "complexity_score", insertable = false, updatable = false) private Integer complexityScore;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "cognitive_metadata", nullable = false, columnDefinition = "jsonb")
    private String cognitiveMetadata = "{}";

    @Enumerated(EnumType.STRING)
    @Column(name = "ai_validation_status", nullable = false, length = 12)
    private AiValidationStatus aiValidationStatus = AiValidationStatus.VERIFIED;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "validation_warnings", nullable = false, columnDefinition = "jsonb")
    private List<QuizDtos.AiValidationWarning> validationWarnings = new ArrayList<>();
    @Column(name = "validation_reviewed_at") private Instant validationReviewedAt;
    @Column(name = "validation_reviewed_by") private UUID validationReviewedBy;
    @Column(name = "validation_review_note", length = 500) private String validationReviewNote;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    @Column(nullable = false)
    private long version;

    protected Question() {}

    public Question(UUID quizId, UUID sourceChunkId, QuestionType type, String prompt, String explanation,
                    BigDecimal points, int position, Difficulty difficulty) {
        this.id = UUID.randomUUID();
        this.quizId = quizId;
        this.sourceChunkId = sourceChunkId;
        this.type = type;
        this.prompt = prompt.trim();
        this.explanation = explanation == null ? null : explanation.trim();
        this.points = points;
        this.position = position;
        this.difficulty = difficulty == null ? Difficulty.MEDIUM : difficulty;
        this.cognitiveLevel = fromLegacy(this.difficulty);
        this.createdAt = Instant.now();
        this.updatedAt = createdAt;
    }

    public void update(UUID sourceChunkId, QuestionType type, String prompt, String explanation,
                       BigDecimal points, Difficulty difficulty) {
        this.sourceChunkId = sourceChunkId;
        this.type = type;
        this.prompt = prompt.trim();
        this.explanation = explanation == null ? null : explanation.trim();
        this.points = points;
        this.difficulty = difficulty;
        this.cognitiveLevel = fromLegacy(difficulty);
        clearCognitiveProfile();
        this.updatedAt = Instant.now();
    }

    public void moveTo(int position) {
        this.position = position;
        this.updatedAt = Instant.now();
    }

    public UUID getId() { return id; }
    public UUID getQuizId() { return quizId; }
    public UUID getSourceChunkId() { return sourceChunkId; }
    public QuestionType getType() { return type; }
    public String getPrompt() { return prompt; }
    public String getExplanation() { return explanation; }
    public BigDecimal getPoints() { return points; }
    public int getPosition() { return position; }
    public Difficulty getDifficulty() { return difficulty; }
    public CognitiveLevel getCognitiveLevel() { return cognitiveLevel; }
    public Integer getConceptCount() { return conceptCount; }
    public Integer getReasoningStepCount() { return reasoningStepCount; }
    public Boolean getRequiresNovelScenario() { return requiresNovelScenario; }
    public Boolean getAnswerDirectlyPresent() { return answerDirectlyPresent; }
    public Boolean getRequiresComparison() { return requiresComparison; }
    public boolean isComplexityVerified() { return complexityVerified; }
    public Integer getComplexityScore() { return complexityScore; }
    public String getCognitiveMetadata() { return cognitiveMetadata; }
    public AiValidationStatus getAiValidationStatus() { return aiValidationStatus; }
    public List<QuizDtos.AiValidationWarning> getValidationWarnings() {
        return List.copyOf(validationWarnings);
    }
    public void applyAiValidation(AiValidationStatus status,
                                  List<QuizDtos.AiValidationWarning> warnings) {
        aiValidationStatus = status == null ? AiValidationStatus.VERIFIED : status;
        validationWarnings = warnings == null
                ? new ArrayList<>() : new ArrayList<>(warnings);
        validationReviewedAt = null;
        validationReviewedBy = null;
        validationReviewNote = null;
    }
    public void markValidationReviewed(UUID reviewerId, String note, Instant now) {
        if (aiValidationStatus != AiValidationStatus.WARNING || validationWarnings.isEmpty()) {
            throw new IllegalStateException("QUESTION_HAS_NO_VALIDATION_WARNING");
        }
        aiValidationStatus = AiValidationStatus.REVIEWED;
        validationReviewedAt = now;
        validationReviewedBy = reviewerId;
        validationReviewNote = note == null || note.isBlank() ? null : note.trim();
        updatedAt = now;
    }
    public void undoValidationReview() {
        if (aiValidationStatus != AiValidationStatus.REVIEWED) {
            throw new IllegalStateException("QUESTION_VALIDATION_NOT_REVIEWED");
        }
        aiValidationStatus = validationWarnings.isEmpty()
                ? AiValidationStatus.VERIFIED : AiValidationStatus.WARNING;
        validationReviewedAt = null;
        validationReviewedBy = null;
        validationReviewNote = null;
        updatedAt = Instant.now();
    }
    public Instant getValidationReviewedAt() { return validationReviewedAt; }
    public UUID getValidationReviewedBy() { return validationReviewedBy; }
    public String getValidationReviewNote() { return validationReviewNote; }
    public void applyCognitiveProfile(CognitiveLevel level, CognitiveProfile profile, String metadata) {
        this.cognitiveLevel = level;
        this.difficulty = switch (level) {
            case L1 -> Difficulty.EASY;
            case L2, L3 -> Difficulty.MEDIUM;
            case L4, L5 -> Difficulty.HARD;
        };
        this.conceptCount = profile.conceptCount();
        this.reasoningStepCount = profile.reasoningStepCount();
        this.requiresNovelScenario = profile.requiresNovelScenario();
        this.answerDirectlyPresent = profile.answerDirectlyPresent();
        this.requiresComparison = profile.requiresComparison();
        this.complexityVerified = profile.verified();
        this.cognitiveMetadata = metadata == null ? "{}" : metadata;
    }
    public long getVersion() { return version; }

    private void clearCognitiveProfile() {
        conceptCount = null;
        reasoningStepCount = null;
        requiresNovelScenario = null;
        answerDirectlyPresent = null;
        requiresComparison = null;
        complexityVerified = false;
        cognitiveMetadata = "{}";
        aiValidationStatus = AiValidationStatus.VERIFIED;
        validationWarnings = new ArrayList<>();
        validationReviewedAt = null;
        validationReviewedBy = null;
        validationReviewNote = null;
    }
    private static CognitiveLevel fromLegacy(Difficulty difficulty) {
        if (difficulty == null) return CognitiveLevel.L3;
        return switch (difficulty) {
            case EASY -> CognitiveLevel.L1;
            case MEDIUM, MIXED -> CognitiveLevel.L3;
            case HARD -> CognitiveLevel.L5;
        };
    }
}
