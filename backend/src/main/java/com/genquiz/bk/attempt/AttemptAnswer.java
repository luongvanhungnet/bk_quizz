package com.genquiz.bk.attempt;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import jakarta.persistence.Version;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "attempt_answers", uniqueConstraints = {
        @UniqueConstraint(name = "uk_attempt_answer_snapshot", columnNames = {"attempt_id", "question_snapshot_id"})
})
public class AttemptAnswer {
    @Id
    private UUID id;

    @Column(name = "attempt_id", nullable = false, updatable = false)
    private UUID attemptId;

    @Column(name = "question_snapshot_id", nullable = false, updatable = false)
    private UUID snapshotId;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "selected_option_ids", nullable = false, columnDefinition = "jsonb")
    private String selectedOptionIds;

    @Column(name = "answer_text", columnDefinition = "text")
    private String textAnswer;

    @Column(name = "is_correct")
    private Boolean correct;

    @Column(name = "awarded_points", precision = 8, scale = 2)
    private BigDecimal awardedPoints;

    @Column(name = "answered_at", nullable = false)
    private Instant answeredAt;

    @Column(name = "graded_at")
    private Instant gradedAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    @Column(nullable = false)
    private long version;

    protected AttemptAnswer() {}

    public AttemptAnswer(UUID attemptId, UUID snapshotId) {
        this.id = UUID.randomUUID();
        this.attemptId = attemptId;
        this.snapshotId = snapshotId;
        this.selectedOptionIds = "[]";
        this.answeredAt = Instant.now();
        this.createdAt = answeredAt;
        this.updatedAt = answeredAt;
    }

    public void save(String selectedOptionIds, String textAnswer, Instant now) {
        this.selectedOptionIds = selectedOptionIds == null ? "[]" : selectedOptionIds;
        this.textAnswer = textAnswer == null ? null : textAnswer.trim();
        this.correct = null;
        this.awardedPoints = null;
        this.gradedAt = null;
        this.answeredAt = now;
        this.updatedAt = now;
    }

    public void grade(boolean correct, BigDecimal points, Instant now) {
        this.correct = correct;
        this.awardedPoints = correct ? points : BigDecimal.ZERO.setScale(2);
        this.gradedAt = now;
        this.updatedAt = now;
    }

    public UUID getId() { return id; }
    public UUID getAttemptId() { return attemptId; }
    public UUID getSnapshotId() { return snapshotId; }
    public String getSelectedOptionIds() { return selectedOptionIds; }
    public String getTextAnswer() { return textAnswer; }
    public Boolean getCorrect() { return correct; }
    public BigDecimal getAwardedPoints() { return awardedPoints; }
    public long getVersion() { return version; }
}
