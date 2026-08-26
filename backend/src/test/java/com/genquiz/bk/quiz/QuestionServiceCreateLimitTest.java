package com.genquiz.bk.quiz;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.genquiz.bk.common.error.ApiException;
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class QuestionServiceCreateLimitTest {
    @Test
    void rejectsManualQuestionWhenQuizAlreadyHasOneHundredQuestions() {
        UUID actorId = UUID.randomUUID();
        UUID quizId = UUID.randomUUID();
        QuestionRepository questions = mock(QuestionRepository.class);
        QuizService quizzes = mock(QuizService.class);
        Quiz quiz = mock(Quiz.class);
        when(quiz.getStatus()).thenReturn(QuizStatus.READY);
        when(quizzes.getOwned(actorId, quizId)).thenReturn(quiz);
        when(questions.countByQuizId(quizId)).thenReturn(100L);
        QuestionService service = new QuestionService(
                questions, mock(QuestionOptionRepository.class),
                mock(AcceptedAnswerRepository.class), quizzes);
        QuizDtos.QuestionRequest request = new QuizDtos.QuestionRequest(
                QuestionType.FILL_BLANK, "Câu 101", null, BigDecimal.ONE,
                Difficulty.MEDIUM, null, List.of(), List.of("Đáp án"));

        ApiException error = assertThrows(ApiException.class,
                () -> service.create(actorId, quizId, request));

        assertEquals("QUIZ_QUESTION_LIMIT_EXCEEDED", error.code());
    }
}
