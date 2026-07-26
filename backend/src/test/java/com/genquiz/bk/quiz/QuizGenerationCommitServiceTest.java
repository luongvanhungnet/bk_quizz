package com.genquiz.bk.quiz;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class QuizGenerationCommitServiceTest {

    private final QuestionService questions = mock(QuestionService.class);
    private final QuizService quizzes = mock(QuizService.class);
    private final QuizGenerationCommitService service = new QuizGenerationCommitService(questions, quizzes);

    @Test
    void marksQuizReadyOnlyAfterQuestionsWereReplaced() {
        UUID quizId = UUID.randomUUID();
        List<QuizDtos.QuestionRequest> generated = List.of();
        QuizDtos.QuestionCounts expected = new QuizDtos.QuestionCounts(0, 0, 0);

        service.replaceAndComplete(quizId, generated, expected);

        var calls = inOrder(questions, quizzes);
        calls.verify(questions).replaceGenerated(quizId, generated, expected);
        calls.verify(quizzes).markReady(quizId);
    }

    @Test
    void doesNotMarkQuizReadyWhenReplacingQuestionsFails() {
        UUID quizId = UUID.randomUUID();
        List<QuizDtos.QuestionRequest> generated = List.of();
        QuizDtos.QuestionCounts expected = new QuizDtos.QuestionCounts(0, 0, 0);
        doThrow(new IllegalStateException("write failed"))
                .when(questions).replaceGenerated(quizId, generated, expected);

        assertThrows(IllegalStateException.class,
                () -> service.replaceAndComplete(quizId, generated, expected));

        verify(quizzes, never()).markReady(quizId);
    }

    @Test
    void commitsGroundedQuestionsAndCitationsBeforeMarkingReady() {
        UUID quizId = UUID.randomUUID();
        List<QuizDtos.GroundedQuestion> generated = List.of();
        QuizDtos.QuestionCounts expected = new QuizDtos.QuestionCounts(0, 0, 0);

        service.replaceGroundedAndComplete(quizId, generated, expected);

        var calls = inOrder(questions, quizzes);
        calls.verify(questions).replaceGrounded(quizId, generated, expected);
        calls.verify(quizzes).markReady(quizId);
    }
}
