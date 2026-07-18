package com.genquiz.bk.quiz;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "quiz_sources")
public class QuizSource {
    @Id
    private UUID id;

    @Column(name = "quiz_id", nullable = false, updatable = false)
    private UUID quizId;

    @Column(name = "source_document_id", nullable = false, updatable = false)
    private UUID sourceDocumentId;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected QuizSource() {}

    public QuizSource(UUID quizId, UUID sourceDocumentId) {
        this.id = UUID.randomUUID();
        this.quizId = quizId;
        this.sourceDocumentId = sourceDocumentId;
        this.createdAt = Instant.now();
    }

    public UUID getQuizId() { return quizId; }
    public UUID getSourceDocumentId() { return sourceDocumentId; }
}
