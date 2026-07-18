package com.genquiz.bk.quiz;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.Locale;
import java.util.UUID;

@Entity
@Table(name = "accepted_answers")
public class AcceptedAnswer {
    @Id
    private UUID id;

    @Column(name = "question_id", nullable = false, updatable = false)
    private UUID questionId;

    @Column(name = "answer_text", nullable = false, columnDefinition = "text")
    private String answerText;

    @Column(name = "normalized_answer", nullable = false, columnDefinition = "citext")
    private String normalizedAnswer;

    @Column(nullable = false)
    private int position;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected AcceptedAnswer() {}

    public AcceptedAnswer(UUID questionId, String answerText, int position) {
        this.id = UUID.randomUUID();
        this.questionId = questionId;
        this.answerText = answerText.trim();
        this.normalizedAnswer = normalize(answerText);
        this.position = position;
        this.createdAt = Instant.now();
    }

    public static String normalize(String value) {
        return value == null ? "" : value.trim().replaceAll("\\s+", " ").toLowerCase(Locale.ROOT);
    }

    public UUID getId() { return id; }
    public UUID getQuestionId() { return questionId; }
    public String getAnswerText() { return answerText; }
    public String getNormalizedAnswer() { return normalizedAnswer; }
    public int getPosition() { return position; }
}
