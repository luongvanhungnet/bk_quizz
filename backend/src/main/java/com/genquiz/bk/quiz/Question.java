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
    public long getVersion() { return version; }
}
