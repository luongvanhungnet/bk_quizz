package com.genquiz.bk.attempt;

import com.genquiz.bk.quiz.QuestionType;
import com.genquiz.bk.quiz.CognitiveLevel;
import com.genquiz.bk.quiz.AiValidationStatus;
import com.genquiz.bk.quiz.QuizDtos;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import java.util.ArrayList;
import java.util.List;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "attempt_question_snapshots")
public class AttemptQuestionSnapshot {
    @Id
    private UUID id;

    @Column(name = "attempt_id", nullable = false, updatable = false)
    private UUID attemptId;

    @Column(name = "source_question_id", updatable = false)
    private UUID sourceQuestionId;

    @Column(name = "source_chunk_id", updatable = false)
    private UUID sourceChunkId;

    @Enumerated(EnumType.STRING)
    @Column(name = "type", nullable = false, length = 30)
    private QuestionType questionType;

    @Column(nullable = false, columnDefinition = "text")
    private String prompt;

    @Column(columnDefinition = "text")
    private String explanation;

    @Column(nullable = false, precision = 8, scale = 2)
    private BigDecimal points;

    @Column(nullable = false)
    private int position;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "options_snapshot", nullable = false, columnDefinition = "jsonb")
    private String optionsPayload;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "answer_key", nullable = false, columnDefinition = "jsonb")
    private String answerKey;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "citations_snapshot", nullable = false, columnDefinition = "jsonb")
    private String citationsPayload;

    @Enumerated(EnumType.STRING)
    @Column(name = "cognitive_level", nullable = false, length = 10)
    private CognitiveLevel cognitiveLevel;
    @Column(name = "complexity_score") private Integer complexityScore;
    @Column(name = "complexity_verified", nullable = false) private boolean complexityVerified;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "cognitive_profile_snapshot", nullable = false, columnDefinition = "jsonb")
    private String cognitiveProfilePayload;

    @Enumerated(EnumType.STRING)
    @Column(name = "ai_validation_status", nullable = false, length = 12)
    private AiValidationStatus aiValidationStatus = AiValidationStatus.VERIFIED;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "validation_warnings_snapshot", nullable = false, columnDefinition = "jsonb")
    private List<QuizDtos.AiValidationWarning> validationWarnings = new ArrayList<>();

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected AttemptQuestionSnapshot() {}

    public AttemptQuestionSnapshot(UUID attemptId, UUID sourceQuestionId, UUID sourceChunkId, QuestionType questionType,
                                   String prompt, String explanation, BigDecimal points, int position,
                                   String optionsPayload, String answerKey) {
        this(attemptId, sourceQuestionId, sourceChunkId, questionType, prompt, explanation, points, position,
                optionsPayload, answerKey, "[]", CognitiveLevel.L3, null, false, "{}");
    }

    public AttemptQuestionSnapshot(UUID attemptId, UUID sourceQuestionId, UUID sourceChunkId, QuestionType questionType,
                                   String prompt, String explanation, BigDecimal points, int position,
                                   String optionsPayload, String answerKey, String citationsPayload) {
        this.id = UUID.randomUUID();
        this.attemptId = attemptId;
        this.sourceQuestionId = sourceQuestionId;
        this.sourceChunkId = sourceChunkId;
        this.questionType = questionType;
        this.prompt = prompt;
        this.explanation = explanation;
        this.points = points;
        this.position = position;
        this.optionsPayload = optionsPayload;
        this.answerKey = answerKey;
        this.citationsPayload = citationsPayload == null ? "[]" : citationsPayload;
        this.cognitiveLevel = CognitiveLevel.L3;
        this.cognitiveProfilePayload = "{}";
        this.createdAt = Instant.now();
    }

    public AttemptQuestionSnapshot(UUID attemptId, UUID sourceQuestionId, UUID sourceChunkId, QuestionType questionType,
                                   String prompt, String explanation, BigDecimal points, int position,
                                   String optionsPayload, String answerKey, String citationsPayload,
                                   CognitiveLevel cognitiveLevel, Integer complexityScore,
                                   boolean complexityVerified, String cognitiveProfilePayload) {
        this(attemptId, sourceQuestionId, sourceChunkId, questionType, prompt, explanation,
                points, position, optionsPayload, answerKey, citationsPayload, cognitiveLevel,
                complexityScore, complexityVerified, cognitiveProfilePayload,
                AiValidationStatus.VERIFIED, List.of());
    }

    public AttemptQuestionSnapshot(UUID attemptId, UUID sourceQuestionId, UUID sourceChunkId,
                                   QuestionType questionType, String prompt, String explanation,
                                   BigDecimal points, int position, String optionsPayload,
                                   String answerKey, String citationsPayload,
                                   CognitiveLevel cognitiveLevel, Integer complexityScore,
                                   boolean complexityVerified, String cognitiveProfilePayload,
                                   AiValidationStatus aiValidationStatus,
                                   List<QuizDtos.AiValidationWarning> validationWarnings) {
        this.id = UUID.randomUUID();
        this.attemptId = attemptId;
        this.sourceQuestionId = sourceQuestionId;
        this.sourceChunkId = sourceChunkId;
        this.questionType = questionType;
        this.prompt = prompt;
        this.explanation = explanation;
        this.points = points;
        this.position = position;
        this.optionsPayload = optionsPayload;
        this.answerKey = answerKey;
        this.citationsPayload = citationsPayload == null ? "[]" : citationsPayload;
        this.cognitiveLevel = cognitiveLevel == null ? CognitiveLevel.L3 : cognitiveLevel;
        this.complexityScore = complexityScore;
        this.complexityVerified = complexityVerified;
        this.cognitiveProfilePayload = cognitiveProfilePayload == null ? "{}" : cognitiveProfilePayload;
        this.aiValidationStatus = aiValidationStatus == null
                ? AiValidationStatus.VERIFIED : aiValidationStatus;
        this.validationWarnings = validationWarnings == null
                ? new ArrayList<>() : new ArrayList<>(validationWarnings);
        this.createdAt = Instant.now();
    }

    public UUID getId() { return id; }
    public UUID getAttemptId() { return attemptId; }
    public UUID getSourceQuestionId() { return sourceQuestionId; }
    public UUID getSourceChunkId() { return sourceChunkId; }
    public QuestionType getQuestionType() { return questionType; }
    public String getPrompt() { return prompt; }
    public String getExplanation() { return explanation; }
    public BigDecimal getPoints() { return points; }
    public int getPosition() { return position; }
    public String getOptionsPayload() { return optionsPayload; }
    public String getAnswerKey() { return answerKey; }
    public String getCitationsPayload() { return citationsPayload; }
    public CognitiveLevel getCognitiveLevel() { return cognitiveLevel; }
    public Integer getComplexityScore() { return complexityScore; }
    public boolean isComplexityVerified() { return complexityVerified; }
    public String getCognitiveProfilePayload() { return cognitiveProfilePayload; }
    public AiValidationStatus getAiValidationStatus() { return aiValidationStatus; }
    public List<QuizDtos.AiValidationWarning> getValidationWarnings() {
        return List.copyOf(validationWarnings);
    }
}
