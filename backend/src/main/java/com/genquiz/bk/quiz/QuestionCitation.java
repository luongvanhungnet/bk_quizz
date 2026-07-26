package com.genquiz.bk.quiz;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "question_citations")
public class QuestionCitation {
    @Id private UUID id;
    @Column(name="question_id", nullable=false, updatable=false) private UUID questionId;
    @Column(name="source_chunk_id", nullable=false, updatable=false) private UUID sourceChunkId;
    @Enumerated(EnumType.STRING) @Column(name="citation_role", nullable=false, length=20) private CitationRole role;
    @Column(name="evidence_quote", nullable=false, columnDefinition="text") private String evidenceQuote;
    @Column(nullable=false) private int position;
    @Column(name="created_at", nullable=false, updatable=false) private Instant createdAt;
    protected QuestionCitation() {}
    public QuestionCitation(UUID questionId, UUID sourceChunkId, CitationRole role, String quote, int position) {
        this.id=UUID.randomUUID(); this.questionId=questionId; this.sourceChunkId=sourceChunkId;
        this.role=role; this.evidenceQuote=quote.trim(); this.position=position; this.createdAt=Instant.now();
    }
    public UUID getQuestionId(){return questionId;} public UUID getSourceChunkId(){return sourceChunkId;}
    public CitationRole getRole(){return role;} public String getEvidenceQuote(){return evidenceQuote;}
    public int getPosition(){return position;}
}
