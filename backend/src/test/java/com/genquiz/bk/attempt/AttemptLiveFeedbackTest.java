package com.genquiz.bk.attempt;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.quiz.AcceptedAnswerRepository;
import com.genquiz.bk.quiz.QuestionCitationRepository;
import com.genquiz.bk.quiz.QuestionOptionRepository;
import com.genquiz.bk.quiz.QuestionRepository;
import com.genquiz.bk.quiz.QuestionType;
import com.genquiz.bk.quiz.QuizService;
import com.genquiz.bk.source.SourceChunkRepository;
import com.genquiz.bk.source.SourceDocumentRepository;
import java.time.Instant;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class AttemptLiveFeedbackTest {
    @Test
    void practiceAttemptSnapshotsTheSelectedLiveFeedbackMode() {
        Instant now = Instant.parse("2026-07-26T00:00:00Z");
        Attempt attempt = new Attempt(
                UUID.randomUUID(), null, UUID.randomUUID(), 1, 3,
                now, now.plusSeconds(600), AnswerReleasePolicy.IMMEDIATE,
                null, true, true, AttemptMode.LIVE_FEEDBACK);

        assertEquals(AttemptMode.LIVE_FEEDBACK, attempt.getMode());
    }

    @Test
    void confirmingAnAnswerLocksItsStoredGrade() {
        Instant now = Instant.parse("2026-07-26T00:00:00Z");
        AttemptAnswer answer = new AttemptAnswer(UUID.randomUUID(), UUID.randomUUID());
        answer.save("[\"00000000-0000-0000-0000-000000000001\"]", null, now);

        answer.confirm(true, BigDecimal.ONE, now.plusSeconds(1));

        assertEquals(true, answer.getCorrect());
        assertEquals(now.plusSeconds(1), answer.getConfirmedAt());
    }

    @Test
    void assignmentCannotEnableLiveFeedback() {
        AttemptService service = service(Clock.systemUTC());

        ApiException error = assertThrows(ApiException.class, () ->
                service.start(UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(),
                        AttemptMode.LIVE_FEEDBACK));

        assertEquals("LIVE_FEEDBACK_NOT_ALLOWED", error.code());
    }

    @Test
    void liveConfirmationIsGradedAndRepeatedIdenticalRequestIsIdempotent() {
        Instant now = Instant.parse("2026-07-26T00:00:00Z");
        UUID actorId = UUID.randomUUID();
        UUID attemptId;
        UUID optionId = UUID.randomUUID();
        Attempt attempt = new Attempt(
                UUID.randomUUID(), null, actorId, 1, 1, now,
                now.plusSeconds(600), AnswerReleasePolicy.IMMEDIATE, null,
                true, true, AttemptMode.LIVE_FEEDBACK);
        attemptId = attempt.getId();
        AttemptQuestionSnapshot snapshot = new AttemptQuestionSnapshot(
                attemptId, UUID.randomUUID(), null, QuestionType.SINGLE_CHOICE,
                "Câu hỏi?", "Giải thích", BigDecimal.ONE, 1,
                "[{\"id\":\"" + optionId + "\",\"text\":\"A\",\"position\":1}]",
                "{\"correctOptionIds\":[\"" + optionId + "\"],\"acceptedAnswers\":[]}",
                "[]");
        AttemptRepository attemptRepository = mock(AttemptRepository.class);
        AttemptQuestionSnapshotRepository snapshotRepository =
                mock(AttemptQuestionSnapshotRepository.class);
        AttemptAnswerRepository answerRepository = mock(AttemptAnswerRepository.class);
        when(attemptRepository.findByIdAndUserId(attemptId, actorId))
                .thenReturn(Optional.of(attempt));
        when(snapshotRepository.findByIdAndAttemptId(snapshot.getId(), attemptId))
                .thenReturn(Optional.of(snapshot));
        final AttemptAnswer[] stored = new AttemptAnswer[1];
        when(answerRepository.save(any())).thenAnswer(invocation -> {
            stored[0] = invocation.getArgument(0);
            return stored[0];
        });
        when(answerRepository.findByAttemptIdAndSnapshotId(attemptId, snapshot.getId()))
                .thenAnswer(invocation -> Optional.ofNullable(stored[0]));
        AttemptService service = service(
                attemptRepository, snapshotRepository, answerRepository,
                Clock.fixed(now.plusSeconds(1), ZoneOffset.UTC));
        var request = new AttemptDtos.ConfirmAnswerRequest(
                attempt.getVersion(), List.of(optionId), null);

        var first = service.confirmAnswer(actorId, attemptId, snapshot.getId(), request);
        var repeated = service.confirmAnswer(actorId, attemptId, snapshot.getId(), request);

        assertEquals(true, first.correct());
        assertEquals(first, repeated);
    }

    private AttemptService service(Clock clock) {
        return service(mock(AttemptRepository.class),
                mock(AttemptQuestionSnapshotRepository.class),
                mock(AttemptAnswerRepository.class), clock);
    }

    private AttemptService service(
            AttemptRepository attempts,
            AttemptQuestionSnapshotRepository snapshots,
            AttemptAnswerRepository answers,
            Clock clock) {
        return new AttemptService(
                attempts, snapshots, answers, mock(QuestionRepository.class),
                mock(QuestionOptionRepository.class),
                mock(AcceptedAnswerRepository.class), mock(QuizService.class),
                mock(AssignmentPolicyGateway.class), new ObjectMapper(), clock,
                mock(QuestionCitationRepository.class),
                mock(SourceChunkRepository.class),
                mock(SourceDocumentRepository.class));
    }
}
