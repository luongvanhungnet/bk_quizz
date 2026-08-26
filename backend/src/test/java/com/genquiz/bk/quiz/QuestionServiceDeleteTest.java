package com.genquiz.bk.quiz;

import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;

class QuestionServiceDeleteTest {

    @Test
    void ownerCanDeleteAQuestionFromAPublishedQuiz() {
        UUID actorId = UUID.randomUUID();
        UUID quizId = UUID.randomUUID();
        Question question = new Question(
                quizId, null, QuestionType.SINGLE_CHOICE, "Câu hỏi", null,
                BigDecimal.ONE, 0, Difficulty.MEDIUM);
        QuestionRepository questions = mock(QuestionRepository.class);
        QuestionOptionRepository options = mock(QuestionOptionRepository.class);
        AcceptedAnswerRepository acceptedAnswers = mock(AcceptedAnswerRepository.class);
        QuizService quizzes = mock(QuizService.class);
        Quiz quiz = mock(Quiz.class);
        when(quiz.getStatus()).thenReturn(QuizStatus.PUBLISHED);
        when(questions.findById(question.getId())).thenReturn(Optional.of(question));
        when(quizzes.getOwned(actorId, quizId)).thenReturn(quiz);

        QuestionService service = new QuestionService(questions, options, acceptedAnswers, quizzes);

        service.delete(actorId, question.getId());

        InOrder order = inOrder(questions);
        order.verify(questions).delete(question);
        order.verify(questions).flush();
    }

    @Test
    void flushesTheDeletedQuestionBeforeCompactingPositionsInTwoPhases() {
        UUID actorId = UUID.randomUUID();
        UUID quizId = UUID.randomUUID();
        Question question = new Question(
                quizId, null, QuestionType.SINGLE_CHOICE, "Câu hỏi", null,
                BigDecimal.ONE, 1, Difficulty.MEDIUM);
        QuestionRepository questions = mock(QuestionRepository.class);
        QuestionOptionRepository options = mock(QuestionOptionRepository.class);
        AcceptedAnswerRepository acceptedAnswers = mock(AcceptedAnswerRepository.class);
        QuestionCitationRepository citations = mock(QuestionCitationRepository.class);
        QuizService quizzes = mock(QuizService.class);
        Quiz quiz = mock(Quiz.class);
        when(quiz.getStatus()).thenReturn(QuizStatus.READY);
        when(questions.findById(question.getId())).thenReturn(Optional.of(question));
        when(quizzes.getOwned(actorId, quizId)).thenReturn(quiz);

        QuestionService service = new QuestionService(
                questions, options, acceptedAnswers, quizzes,
                citations, null, null, null);

        service.delete(actorId, question.getId());

        InOrder order = inOrder(questions);
        order.verify(questions).delete(question);
        order.verify(questions).flush();
        order.verify(questions).movePositionsAfterToTemporaryRange(quizId, 1, 1000);
        order.verify(questions).restoreTemporaryPositionsAfterDelete(quizId, 1000);
    }
}
