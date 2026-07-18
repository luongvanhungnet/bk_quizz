package com.genquiz.bk.quiz;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "question_options")
public class QuestionOption {
    @Id
    private UUID id;

    @Column(name = "question_id", nullable = false, updatable = false)
    private UUID questionId;

    @Column(name = "option_text", nullable = false, columnDefinition = "text")
    private String optionText;

    @Column(name = "is_correct", nullable = false)
    private boolean correct;

    @Column(nullable = false)
    private int position;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected QuestionOption() {}

    public QuestionOption(UUID questionId, String optionText, boolean correct, int position) {
        this.id = UUID.randomUUID();
        this.questionId = questionId;
        this.optionText = optionText.trim();
        this.correct = correct;
        this.position = position;
        this.createdAt = Instant.now();
    }

    public UUID getId() { return id; }
    public UUID getQuestionId() { return questionId; }
    public String getOptionText() { return optionText; }
    public boolean isCorrect() { return correct; }
    public int getPosition() { return position; }
}
