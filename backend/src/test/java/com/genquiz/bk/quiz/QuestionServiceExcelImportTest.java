package com.genquiz.bk.quiz;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.when;

import com.genquiz.bk.common.error.ApiException;
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class QuestionServiceExcelImportTest {

    @Test
    void importsQuestionsIntoAPublishedQuizInOneTransactionBoundary() {
        UUID actorId = UUID.randomUUID();
        UUID quizId = UUID.randomUUID();
        QuestionRepository questions = mock(QuestionRepository.class);
        QuestionOptionRepository options = mock(QuestionOptionRepository.class);
        AcceptedAnswerRepository acceptedAnswers = mock(AcceptedAnswerRepository.class);
        QuizService quizzes = mock(QuizService.class);
        Quiz quiz = mock(Quiz.class);
        when(quiz.getStatus()).thenReturn(QuizStatus.PUBLISHED);
        when(quizzes.getOwned(actorId, quizId)).thenReturn(quiz);
        when(questions.findByQuizIdOrderByPosition(quizId)).thenReturn(List.of());
        when(questions.save(any())).thenAnswer(invocation -> invocation.getArgument(0));
        QuestionService service = new QuestionService(questions, options, acceptedAnswers, quizzes);
        var first = new QuizDtos.QuestionRequest(QuestionType.SINGLE_CHOICE, "Câu 1", null,
                BigDecimal.ONE, null, CognitiveLevel.L1, null, null,
                List.of(new QuizDtos.OptionRequest("A", true), new QuizDtos.OptionRequest("B", false),
                        new QuizDtos.OptionRequest("C", false), new QuizDtos.OptionRequest("D", false)), List.of());
        var second = new QuizDtos.QuestionRequest(QuestionType.FILL_BLANK, "Câu 2", null,
                BigDecimal.ONE, null, CognitiveLevel.L2, null, null, List.of(), List.of("đáp án"));

        var result = service.importQuestions(actorId, quizId, List.of(
                new QuestionExcelWorkbook.ParsedQuestion(2, first),
                new QuestionExcelWorkbook.ParsedQuestion(3, second)));

        assertEquals(2, result.importedCount());
        assertEquals(2, result.totalQuestionCount());
        verify(questions, times(2)).save(any());
        verify(quizzes).refreshAiValidationStatus(quizId);
    }

    @Test
    void duplicatePromptRollsBackTheWholeImportBeforeSavingAnything() {
        UUID actorId = UUID.randomUUID();
        UUID quizId = UUID.randomUUID();
        Question existing = new Question(quizId, null, QuestionType.SINGLE_CHOICE,
                "Câu hỏi đã có", null, BigDecimal.ONE, 0, Difficulty.MEDIUM);
        QuestionRepository questions = mock(QuestionRepository.class);
        QuestionOptionRepository options = mock(QuestionOptionRepository.class);
        AcceptedAnswerRepository acceptedAnswers = mock(AcceptedAnswerRepository.class);
        QuizService quizzes = mock(QuizService.class);
        Quiz quiz = mock(Quiz.class);
        when(quiz.getStatus()).thenReturn(QuizStatus.READY);
        when(quizzes.getOwned(actorId, quizId)).thenReturn(quiz);
        when(questions.findByQuizIdOrderByPosition(quizId)).thenReturn(List.of(existing));
        QuestionService service = new QuestionService(questions, options, acceptedAnswers, quizzes);
        var duplicate = new QuizDtos.QuestionRequest(QuestionType.FILL_BLANK,
                "  CÂU HỎI  ĐÃ CÓ  ", null, BigDecimal.ONE, null, CognitiveLevel.L2,
                null, null, List.of(), List.of("đáp án"));

        ApiException error = assertThrows(ApiException.class, () -> service.importQuestions(
                actorId, quizId, List.of(new QuestionExcelWorkbook.ParsedQuestion(4, duplicate))));

        assertEquals("DUPLICATE_QUESTION", error.errors().get(0).code());
        assertEquals("CauHoi!B4", error.errors().get(0).field());
        verify(questions, never()).save(any());
    }
}
