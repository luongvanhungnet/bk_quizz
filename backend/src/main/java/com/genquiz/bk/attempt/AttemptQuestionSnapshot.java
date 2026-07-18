package com.genquiz.bk.attempt;

import com.genquiz.bk.quiz.QuestionType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
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

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected AttemptQuestionSnapshot() {}

    public AttemptQuestionSnapshot(UUID attemptId, UUID sourceQuestionId, UUID sourceChunkId, QuestionType questionType,
                                   String prompt, String explanation, BigDecimal points, int position,
                                   String optionsPayload, String answerKey) {
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
}
