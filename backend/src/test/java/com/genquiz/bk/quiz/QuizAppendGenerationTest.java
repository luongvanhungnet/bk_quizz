package com.genquiz.bk.quiz;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.genquiz.bk.config.QuizGenerationBatchProperties;
import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.job.Job;
import com.genquiz.bk.job.JobService;
import com.genquiz.bk.security.VerifiedAccountGuard;
import com.genquiz.bk.source.SourceDocument;
import com.genquiz.bk.source.SourceDocumentRepository;
import com.genquiz.bk.topic.TopicService;
import com.genquiz.bk.topic.Visibility;
import java.time.Clock;
import java.time.Duration;
import java.math.BigDecimal;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import tools.jackson.databind.ObjectMapper;

class QuizAppendGenerationTest {
    @Test
    void keepsExistingQuizSourceRowsAndOnlyInsertsNewLinks() {
        UUID actorId = UUID.randomUUID();
        UUID topicId = UUID.randomUUID();
        UUID existingSourceId = UUID.randomUUID();
        UUID newSourceId = UUID.randomUUID();
        Quiz quiz = Quiz.manual(
                topicId, actorId, "Quiz", null,
                Difficulty.MEDIUM, 30, Visibility.PRIVATE);
        QuizRepository quizzes = mock(QuizRepository.class);
        QuizSourceRepository quizSources = mock(QuizSourceRepository.class);
        QuestionRepository questions = mock(QuestionRepository.class);
        SourceDocumentRepository sources = mock(SourceDocumentRepository.class);
        JobService jobs = mock(JobService.class);
        when(quizzes.findLockedActiveById(quiz.getId()))
                .thenReturn(java.util.Optional.of(quiz));
        when(jobs.hasActiveQuizGeneration(quiz.getId())).thenReturn(false);
        when(questions.findByQuizIdOrderByPosition(quiz.getId()))
                .thenReturn(java.util.stream.IntStream.range(0, 99)
                        .mapToObj(index -> new Question(
                                quiz.getId(), null, QuestionType.FILL_BLANK,
                                "Câu " + index, null, BigDecimal.ONE, index,
                                Difficulty.MEDIUM))
                        .toList());
        when(quizSources.findByQuizId(quiz.getId()))
                .thenReturn(List.of(new QuizSource(quiz.getId(), existingSourceId)));
        SourceDocument existing = mock(SourceDocument.class);
        SourceDocument added = mock(SourceDocument.class);
        when(existing.getTopicId()).thenReturn(topicId);
        when(added.getTopicId()).thenReturn(topicId);
        when(sources.findAllByIdInAndOwnerIdAndStatusAndDeletedAtIsNull(
                any(), any(), any())).thenReturn(List.of(existing, added));
        when(jobs.enqueue(any(), any(), any(), anyString(), anyString(), anyInt()))
                .thenReturn(mock(Job.class));
        QuizService service = new QuizService(
                quizzes, quizSources, questions, sources,
                mock(TopicService.class), jobs, new ObjectMapper(),
                mock(VerifiedAccountGuard.class),
                new QuizGenerationBatchProperties(
                        20, 3, Duration.ofMinutes(5), Duration.ofSeconds(15)),
                Clock.systemUTC());

        service.appendGeneration(
                actorId,
                quiz.getId(),
                new QuizDtos.AppendGenerateRequest(
                        List.of(existingSourceId, newSourceId),
                        CognitiveMode.L3,
                        new QuizDtos.QuestionCounts(1, 0, 0)),
                "request-1");

        verify(quizSources, never()).deleteByQuizId(quiz.getId());
        @SuppressWarnings("unchecked")
        ArgumentCaptor<Iterable<QuizSource>> inserted =
                ArgumentCaptor.forClass(Iterable.class);
        verify(quizSources).saveAll(inserted.capture());
        Set<UUID> insertedIds = java.util.stream.StreamSupport.stream(
                        inserted.getValue().spliterator(), false)
                .map(QuizSource::getSourceDocumentId)
                .collect(java.util.stream.Collectors.toSet());
        org.junit.jupiter.api.Assertions.assertEquals(Set.of(newSourceId), insertedIds);
    }

    @Test
    void rejectsTheOneHundredAndFirstQuestion() {
        UUID actorId = UUID.randomUUID();
        UUID topicId = UUID.randomUUID();
        UUID sourceId = UUID.randomUUID();
        Quiz quiz = Quiz.manual(topicId, actorId, "Quiz", null,
                Difficulty.MEDIUM, 30, Visibility.PRIVATE);
        QuizRepository quizzes = mock(QuizRepository.class);
        QuestionRepository questions = mock(QuestionRepository.class);
        JobService jobs = mock(JobService.class);
        when(quizzes.findLockedActiveById(quiz.getId()))
                .thenReturn(java.util.Optional.of(quiz));
        when(jobs.hasActiveQuizGeneration(quiz.getId())).thenReturn(false);
        when(questions.findByQuizIdOrderByPosition(quiz.getId()))
                .thenReturn(java.util.stream.IntStream.range(0, 100)
                        .mapToObj(index -> new Question(
                                quiz.getId(), null, QuestionType.FILL_BLANK,
                                "Câu " + index, null, BigDecimal.ONE, index,
                                Difficulty.MEDIUM))
                        .toList());
        QuizService service = new QuizService(
                quizzes, mock(QuizSourceRepository.class), questions,
                mock(SourceDocumentRepository.class), mock(TopicService.class),
                jobs, new ObjectMapper(), mock(VerifiedAccountGuard.class),
                new QuizGenerationBatchProperties(
                        20, 3, Duration.ofMinutes(5), Duration.ofSeconds(15)),
                Clock.systemUTC());

        ApiException error = assertThrows(ApiException.class, () ->
                service.appendGeneration(actorId, quiz.getId(),
                        new QuizDtos.AppendGenerateRequest(
                                List.of(sourceId), CognitiveMode.L3,
                                new QuizDtos.QuestionCounts(1, 0, 0)),
                        "request-2"));

        assertEquals("QUIZ_QUESTION_LIMIT_EXCEEDED", error.code());
    }
}
