package com.genquiz.bk.quiz;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.genquiz.bk.source.SourceChunk;
import com.genquiz.bk.source.SourceChunkRepository;
import com.genquiz.bk.source.SourceDocumentRepository;
import com.genquiz.bk.source.SourceDocument;
import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.web.server.ResponseStatusException;

class QuestionServiceGroundingTest {
    private QuestionRepository questions;
    private QuestionCitationRepository citations;
    private SourceChunkRepository sourceChunks;
    private SourceDocumentRepository sourceDocuments;
    private QuizSourceRepository quizSources;
    private QuestionService service;

    @BeforeEach
    void setUp() {
        questions = mock(QuestionRepository.class);
        citations = mock(QuestionCitationRepository.class);
        sourceChunks = mock(SourceChunkRepository.class);
        sourceDocuments = mock(SourceDocumentRepository.class);
        quizSources = mock(QuizSourceRepository.class);
        service = new QuestionService(
                questions,
                mock(QuestionOptionRepository.class),
                mock(AcceptedAnswerRepository.class),
                mock(QuizService.class),
                citations,
                sourceChunks,
                sourceDocuments,
                quizSources);
        when(questions.findByQuizIdOrderByPosition(any())).thenReturn(List.of());
        when(questions.save(any())).thenAnswer(invocation -> invocation.getArgument(0));
        when(sourceChunks.save(any())).thenAnswer(invocation -> invocation.getArgument(0));
    }

    @Test
    void remapsAStaleRagChunkIdByCanonicalQuoteInsideAllowedSources() {
        UUID quizId = UUID.randomUUID();
        UUID sourceId = UUID.randomUUID();
        UUID staleChunkId = UUID.randomUUID();
        UUID currentChunkId = UUID.randomUUID();
        SourceChunk current = chunk(
                currentChunkId, sourceId,
                "Năng lượng của véc-tơ cơ sở bằng một trong khoảng thời gian T.");
        allow(quizId, sourceId, List.of(current));
        when(sourceChunks.findById(staleChunkId)).thenReturn(Optional.empty());

        service.replaceGrounded(
                quizId,
                List.of(grounded(staleChunkId, "năng lượng của véc-tơ cơ sở bằng một")),
                new QuizDtos.QuestionCounts(1, 0, 0));

        @SuppressWarnings("unchecked")
        ArgumentCaptor<Iterable<QuestionCitation>> saved =
                ArgumentCaptor.forClass(Iterable.class);
        verify(citations).saveAll(saved.capture());
        QuestionCitation citation = saved.getValue().iterator().next();
        assertEquals(currentChunkId, citation.getSourceChunkId());
    }

    @Test
    void dropsAnUnverifiableCitationAndKeepsTheUsableQuestionWithWarning() {
        UUID quizId = UUID.randomUUID();
        UUID sourceId = UUID.randomUUID();
        UUID staleChunkId = UUID.randomUUID();
        allow(quizId, sourceId, List.of());
        when(sourceChunks.findById(staleChunkId)).thenReturn(Optional.empty());

        service.replaceGrounded(
                quizId,
                List.of(grounded(staleChunkId, "đoạn không còn trong chỉ mục")),
                new QuizDtos.QuestionCounts(1, 0, 0));

        ArgumentCaptor<Question> savedQuestion = ArgumentCaptor.forClass(Question.class);
        verify(questions).save(savedQuestion.capture());
        assertEquals(AiValidationStatus.WARNING,
                savedQuestion.getValue().getAiValidationStatus());
        assertEquals("INVALID_CITATION_QUOTE",
                savedQuestion.getValue().getValidationWarnings().get(0).code());
        assertEquals(null, savedQuestion.getValue().getSourceChunkId());
    }

    @Test
    void stillRejectsCitationThatResolvesToAnUnselectedSource() {
        UUID quizId = UUID.randomUUID();
        UUID allowedSourceId = UUID.randomUUID();
        UUID forbiddenSourceId = UUID.randomUUID();
        UUID chunkId = UUID.randomUUID();
        allow(quizId, allowedSourceId, List.of());
        when(sourceChunks.findById(chunkId)).thenReturn(Optional.of(
                chunk(chunkId, forbiddenSourceId, "Nội dung ngoài nguồn đã chọn.")));

        ResponseStatusException error = assertThrows(
                ResponseStatusException.class, () -> service.replaceGrounded(
                quizId,
                List.of(grounded(chunkId, "Nội dung ngoài nguồn đã chọn")),
                new QuizDtos.QuestionCounts(1, 0, 0)));
        assertEquals("QUIZ_CITATION_SOURCE_FORBIDDEN", error.getReason());
    }

    @Test
    void persistsTrustedRagChunkSnapshotBeforeSavingCitation() {
        UUID quizId = UUID.randomUUID();
        UUID sourceId = UUID.randomUUID();
        UUID topicId = UUID.randomUUID();
        UUID ragDocumentId = UUID.randomUUID();
        UUID chunkId = UUID.randomUUID();
        SourceDocument document = mock(SourceDocument.class);
        when(document.getId()).thenReturn(sourceId);
        when(document.getTopicId()).thenReturn(topicId);
        when(document.getRagDocumentId()).thenReturn(ragDocumentId);
        when(sourceDocuments.findByIdAndDeletedAtIsNull(sourceId)).thenReturn(Optional.of(document));
        allow(quizId, sourceId, List.of());
        when(sourceChunks.findById(chunkId)).thenReturn(Optional.empty());

        var base = grounded(chunkId, "b_i^*(t)=0 nghĩa là phụ thuộc tuyến tính");
        var snapshotCitation = new QuizDtos.CitationRequest(
                chunkId, CitationRole.QUESTION,
                "b_i^*(t)=0 nghĩa là phụ thuộc tuyến tính",
                ragDocumentId, 14, 6, null, "Gram-Schmidt",
                "Nếu b_i^*(t)=0 nghĩa là phụ thuộc tuyến tính và không tạo véc-tơ cơ sở mới.",
                "Neu b_i*(t)=0 nghia la phu thuoc tuyen tinh.", true, "abc123");
        var generated = new QuizDtos.GroundedQuestion(
                base.question(), List.of(snapshotCitation));

        service.replaceGrounded(quizId, List.of(generated),
                new QuizDtos.QuestionCounts(1, 0, 0));

        ArgumentCaptor<SourceChunk> snapshot = ArgumentCaptor.forClass(SourceChunk.class);
        verify(sourceChunks).save(snapshot.capture());
        assertEquals(chunkId, snapshot.getValue().getId());
        assertEquals(sourceId, snapshot.getValue().getSourceDocumentId());
        assertEquals("abc123", snapshot.getValue().getSnapshotFingerprint());
        verify(citations).saveAll(any());
    }

    private void allow(UUID quizId, UUID sourceId, List<SourceChunk> chunks) {
        when(quizSources.findByQuizId(quizId))
                .thenReturn(List.of(new QuizSource(quizId, sourceId)));
        when(sourceChunks.findBySourceDocumentIdOrderByChunkIndex(sourceId))
                .thenReturn(chunks);
    }

    private static SourceChunk chunk(UUID id, UUID sourceId, String content) {
        return new SourceChunk(
                id, sourceId, UUID.randomUUID(), 0, content, 10,
                1, null, null, content, false);
    }

    private static QuizDtos.GroundedQuestion grounded(UUID chunkId, String quote) {
        var question = new QuizDtos.QuestionRequest(
                QuestionType.SINGLE_CHOICE,
                "Câu hỏi có đủ cấu trúc?",
                "Giải thích",
                BigDecimal.ONE,
                Difficulty.MEDIUM,
                null,
                List.of(
                        new QuizDtos.OptionRequest("A", true),
                        new QuizDtos.OptionRequest("B", false),
                        new QuizDtos.OptionRequest("C", false),
                        new QuizDtos.OptionRequest("D", false)),
                List.of());
        return new QuizDtos.GroundedQuestion(
                question,
                List.of(new QuizDtos.CitationRequest(
                        chunkId, CitationRole.QUESTION, quote)));
    }
}
