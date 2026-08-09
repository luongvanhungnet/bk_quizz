package com.genquiz.bk.quiz;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.when;

import com.genquiz.bk.job.Job;
import com.genquiz.bk.job.JobService;
import com.genquiz.bk.job.JobType;
import com.genquiz.bk.job.JobDeferredException;
import com.genquiz.bk.rag.RagClient;
import com.genquiz.bk.rag.RagDtos;
import com.genquiz.bk.source.SourceDocument;
import com.genquiz.bk.source.SourceDocumentRepository;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataIntegrityViolationException;
import org.mockito.ArgumentCaptor;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.JsonNode;

class QuizGenerationCheckpointTest {
    @Test
    void structuredOutputCheckpointRestoresModelAndUsageAfterResume() throws Exception {
        var plans = QuizGenerationBatchPlanner.plan(
                new QuizDtos.QuestionCounts(1, 0, 0),
                CognitiveMode.L3,
                20);
        var checkpoint = QuizGenerationCheckpoint.create("fingerprint", plans);
        JsonNode event = new ObjectMapper().readTree("""
                {"type":"STRUCTURED_OUTPUT_CHECKPOINT",
                 "acceptedQuestions":[{"planSlotId":"B1Q1"}],
                 "model":"gemini-3.5-flash-lite",
                 "usage":{"inputTokens":100,"outputTokens":200,"totalTokens":300}}
                """);
        checkpoint = checkpoint.partial(0, event);
        var resumed = new RagDtos.GeneratedQuiz(
                List.of(), "checkpoint", Map.of(
                "inputTokens", 0, "outputTokens", 0, "totalTokens", 0));

        RagDtos.GeneratedQuiz restored = checkpoint.restorePartialAccounting(0, resumed);

        assertEquals("gemini-3.5-flash-lite", restored.model());
        assertEquals(300, restored.usage().get("totalTokens"));
        assertTrue(checkpoint.batches().get(0).partialQuestions().isArray());
    }

    @Test
    void fiftyQuestionsUseThreeGeminiCallsAndCompletedBatchesAreNotRepeated() throws Exception {
        UUID ownerId = UUID.randomUUID();
        UUID quizId = UUID.randomUUID();
        UUID sourceId = UUID.randomUUID();
        UUID ragDocumentId = UUID.randomUUID();
        String payload = """
                {"quizId":"%s","sourceIds":["%s"],"title":"RAG","difficulty":"MIXED",
                 "questionCounts":{"singleChoice":50,"multipleSelect":0,"fillBlank":0}}
                """.formatted(quizId, sourceId);
        Job job = new Job(JobType.QUIZ_GENERATION, ownerId, quizId, payload, "batch-checkpoint", 9, Instant.now());
        ObjectMapper mapper = new ObjectMapper();

        QuizService quizzes = mock(QuizService.class);
        QuizGenerationCommitService commit = mock(QuizGenerationCommitService.class);
        SourceDocumentRepository sources = mock(SourceDocumentRepository.class);
        RagClient rag = mock(RagClient.class);
        JobService jobs = mock(JobService.class);
        SourceDocument source = mock(SourceDocument.class);
        when(source.getId()).thenReturn(sourceId);
        when(source.getRagDocumentId()).thenReturn(ragDocumentId);
        when(source.getIndexedAt()).thenReturn(Instant.parse("2026-07-25T00:00:00Z"));
        when(source.getChunkCount()).thenReturn(1);
        when(sources.findById(sourceId)).thenReturn(java.util.Optional.of(source));
        doAnswer(invocation -> {
            job.checkpoint(invocation.getArgument(1), Instant.now());
            return null;
        }).when(jobs).checkpoint(any(), anyString());
        when(rag.generateStreaming(any(), any(), any(), any())).thenAnswer(invocation -> {
            RagDtos.GenerateRequest request = invocation.getArgument(2);
            return generatedSingleChoiceBatch(
                    request.questionCounts().singleChoice(), ragDocumentId);
        });

        QuizGenerationHandler handler = new QuizGenerationHandler(
                quizzes, commit, sources, mapper, rag, jobs);

        assertThrows(JobDeferredException.class, () -> handler.handle(job));
        assertThrows(JobDeferredException.class, () -> handler.handle(job));
        handler.handle(job);

        ArgumentCaptor<RagDtos.GenerateRequest> requests =
                ArgumentCaptor.forClass(RagDtos.GenerateRequest.class);
        verify(rag, times(3)).generateStreaming(any(), any(), requests.capture(), any());
        verify(rag, times(3)).requireQuizGenerationContract();
        assertEquals(List.of(20, 20, 10), requests.getAllValues().stream()
                .map(request -> request.questionCounts().singleChoice()).toList());
        assertEquals(20, requests.getAllValues().get(1).excludedPrompts().size());
        assertEquals(40, requests.getAllValues().get(2).excludedPrompts().size());
        assertNull(requests.getAllValues().get(0).difficultyPlan(),
                "Cognitive levels must only be sent through questionPlan");
        assertTrue(requests.getAllValues().get(0).acceptedQuestions().isArray(),
                "An empty checkpoint must be serialized as [] instead of null");
        assertEquals(0, requests.getAllValues().get(0).acceptedQuestions().size());
        verify(commit).replaceGroundedAndComplete(any(), any(), any());
    }

    @Test
    void databaseRetryReusesCheckpointWithoutCallingGeminiAgain() throws Exception {
        UUID ownerId = UUID.randomUUID();
        UUID quizId = UUID.randomUUID();
        UUID sourceId = UUID.randomUUID();
        UUID ragDocumentId = UUID.randomUUID();
        UUID chunkId = UUID.randomUUID();
        String payload = """
                {"quizId":"%s","sourceIds":["%s"],"title":"RAG","difficulty":"MIXED",
                 "questionCounts":{"singleChoice":1,"multipleSelect":0,"fillBlank":0}}
                """.formatted(quizId, sourceId);
        Job job = new Job(JobType.QUIZ_GENERATION, ownerId, quizId, payload, "checkpoint", 3, Instant.now());
        ObjectMapper mapper = new ObjectMapper();

        QuizService quizzes = mock(QuizService.class);
        QuizGenerationCommitService commit = mock(QuizGenerationCommitService.class);
        SourceDocumentRepository sources = mock(SourceDocumentRepository.class);
        RagClient rag = mock(RagClient.class);
        JobService jobs = mock(JobService.class);
        SourceDocument source = mock(SourceDocument.class);
        when(source.getId()).thenReturn(sourceId);
        when(source.getRagDocumentId()).thenReturn(ragDocumentId);
        when(source.getIndexedAt()).thenReturn(Instant.parse("2026-07-25T00:00:00Z"));
        when(source.getChunkCount()).thenReturn(1);
        when(sources.findById(sourceId)).thenReturn(java.util.Optional.of(source));
        RagDtos.Citation citation = new RagDtos.Citation(
                chunkId, ragDocumentId, "lesson.txt", null, null, 0, null, "Nguồn hợp lệ");
        RagDtos.GeneratedQuestion question = new RagDtos.GeneratedQuestion(
                "SINGLE_CHOICE", "MEDIUM", "Câu hỏi?", "Giải thích",
                List.of(
                        new RagDtos.Option("A", true), new RagDtos.Option("B", false),
                        new RagDtos.Option("C", false), new RagDtos.Option("D", false)),
                List.of(), List.of(citation), List.of(citation), List.of(citation));
        when(rag.generateStreaming(any(), any(), any(), any())).thenReturn(
                new RagDtos.GeneratedQuiz(List.of(question), "gemini", Map.of("totalTokens", 10)));
        doAnswer(invocation -> {
            job.checkpoint(invocation.getArgument(1), Instant.now());
            return null;
        }).when(jobs).checkpoint(any(), anyString());
        doThrow(new DataIntegrityViolationException("temporary commit failure"))
                .doNothing()
                .when(commit).replaceGroundedAndComplete(any(), any(), any());

        QuizGenerationHandler handler = new QuizGenerationHandler(
                quizzes, commit, sources, mapper, rag, jobs);

        assertThrows(DataIntegrityViolationException.class, () -> handler.handle(job));
        handler.handle(job);

        verify(rag).generateStreaming(any(), any(), any(), any());
    }

    private RagDtos.GeneratedQuiz generatedSingleChoiceBatch(
            int size, UUID documentId) {
        List<RagDtos.GeneratedQuestion> questions = java.util.stream.IntStream
                .range(0, size)
                .mapToObj(index -> {
                    UUID chunkId = UUID.randomUUID();
                    RagDtos.Citation citation = new RagDtos.Citation(
                            chunkId, documentId, "lesson.txt", null, null,
                            index, null, "Nguồn hợp lệ " + index);
                    return new RagDtos.GeneratedQuestion(
                            "SINGLE_CHOICE", null, "Câu hỏi " + index + "?",
                            "Giải thích",
                            List.of(
                                    new RagDtos.Option("A", true),
                                    new RagDtos.Option("B", false),
                                    new RagDtos.Option("C", false),
                                    new RagDtos.Option("D", false)),
                            List.of(), List.of(citation), List.of(citation),
                            List.of(citation));
                }).toList();
        return new RagDtos.GeneratedQuiz(
                questions, "gemini", Map.of("totalTokens", size * 10));
    }
}
