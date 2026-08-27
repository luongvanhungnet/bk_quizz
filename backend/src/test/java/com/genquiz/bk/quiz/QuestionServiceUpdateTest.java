package com.genquiz.bk.quiz;

import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;

class QuestionServiceUpdateTest {

    @Test
    void ownerCanEditAQuestionInAPublishedQuiz() {
        UUID actorId = UUID.randomUUID();
        UUID quizId = UUID.randomUUID();
        Question question = new Question(
                quizId, null, QuestionType.SINGLE_CHOICE, "Câu cũ", null,
                BigDecimal.ONE, 0, Difficulty.MEDIUM);
        QuestionRepository questions = mock(QuestionRepository.class);
        QuestionOptionRepository options = mock(QuestionOptionRepository.class);
        AcceptedAnswerRepository acceptedAnswers = mock(AcceptedAnswerRepository.class);
        QuizService quizzes = mock(QuizService.class);
        Quiz quiz = mock(Quiz.class);
        when(quiz.getStatus()).thenReturn(QuizStatus.PUBLISHED);
        when(questions.findById(question.getId())).thenReturn(Optional.of(question));
        when(quizzes.getOwned(actorId, quizId)).thenReturn(quiz);
        when(options.findByQuestionIdOrderByPosition(question.getId())).thenReturn(List.of());
        when(acceptedAnswers.findByQuestionIdOrderByPosition(question.getId())).thenReturn(List.of());
        when(options.save(any())).thenAnswer(invocation -> invocation.getArgument(0));

        QuestionService service = new QuestionService(questions, options, acceptedAnswers, quizzes);
        QuizDtos.QuestionRequest request = new QuizDtos.QuestionRequest(
                QuestionType.SINGLE_CHOICE, "Câu đã sửa", "Giải thích", BigDecimal.ONE,
                Difficulty.MEDIUM, CognitiveLevel.L2, null, null,
                List.of(
                        new QuizDtos.OptionRequest("A", true),
                        new QuizDtos.OptionRequest("B", false),
                        new QuizDtos.OptionRequest("C", false),
                        new QuizDtos.OptionRequest("D", false)),
                List.of());

        assertDoesNotThrow(() -> service.update(actorId, question.getId(), request));
    }

    @Test
    void manualEditClearsThePreviousSourceChunk() {
        UUID actorId = UUID.randomUUID();
        UUID quizId = UUID.randomUUID();
        UUID sourceChunkId = UUID.randomUUID();
        Question question = new Question(
                quizId, sourceChunkId, QuestionType.SINGLE_CHOICE, "Câu cũ", null,
                BigDecimal.ONE, 0, Difficulty.MEDIUM);
        QuestionRepository questions = mock(QuestionRepository.class);
        QuestionOptionRepository options = mock(QuestionOptionRepository.class);
        AcceptedAnswerRepository acceptedAnswers = mock(AcceptedAnswerRepository.class);
        QuestionCitationRepository citations = mock(QuestionCitationRepository.class);
        QuizService quizzes = mock(QuizService.class);
        Quiz quiz = mock(Quiz.class);
        when(quiz.getStatus()).thenReturn(QuizStatus.READY);
        when(questions.findById(question.getId())).thenReturn(Optional.of(question));
        when(quizzes.getOwned(actorId, quizId)).thenReturn(quiz);
        when(options.findByQuestionIdOrderByPosition(question.getId())).thenReturn(List.of());
        when(acceptedAnswers.findByQuestionIdOrderByPosition(question.getId())).thenReturn(List.of());
        when(citations.findByQuestionIdOrderByRoleAscPositionAsc(question.getId())).thenReturn(List.of());
        when(options.save(any())).thenAnswer(invocation -> invocation.getArgument(0));

        QuestionService service = new QuestionService(
                questions, options, acceptedAnswers, quizzes,
                citations, null, null, null);
        QuizDtos.QuestionRequest request = new QuizDtos.QuestionRequest(
                QuestionType.SINGLE_CHOICE,
                "Câu đã sửa",
                "Giải thích",
                BigDecimal.ONE,
                Difficulty.MEDIUM,
                CognitiveLevel.L2,
                null,
                sourceChunkId,
                List.of(
                        new QuizDtos.OptionRequest("A", true),
                        new QuizDtos.OptionRequest("B", false),
                        new QuizDtos.OptionRequest("C", false),
                        new QuizDtos.OptionRequest("D", false)),
                List.of());

        service.update(actorId, question.getId(), request);

        assertNull(question.getSourceChunkId());
        InOrder optionWrites = inOrder(options);
        optionWrites.verify(options).deleteByQuestionId(question.getId());
        optionWrites.verify(options).flush();
        optionWrites.verify(options).saveAll(any());
    }
}
