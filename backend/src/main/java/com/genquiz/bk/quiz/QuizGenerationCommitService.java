package com.genquiz.bk.quiz;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Service
public class QuizGenerationCommitService {
    private final QuestionService questions;
    private final QuizService quizzes;

    public QuizGenerationCommitService(QuestionService questions, QuizService quizzes) {
        this.questions = questions;
        this.quizzes = quizzes;
    }

    @Transactional
    public void replaceAndComplete(UUID quizId, List<QuizDtos.QuestionRequest> generated,
                                   QuizDtos.QuestionCounts expected) {
        questions.replaceGenerated(quizId, generated, expected);
        quizzes.markReady(quizId);
    }

    @Transactional
    public void replaceGroundedAndComplete(UUID quizId, List<QuizDtos.GroundedQuestion> generated,
                                           QuizDtos.QuestionCounts expected) {
        questions.replaceGrounded(quizId, generated, expected);
        quizzes.markReady(quizId);
    }

    @Transactional
    public void replaceGroundedAndComplete(
            UUID quizId,
            List<QuizDtos.GroundedQuestion> generated,
            QuizDtos.QuestionCounts expected,
            AiValidationStatus validationStatus,
            List<QuizDtos.AiValidationWarning> validationWarnings) {
        questions.replaceGrounded(quizId, generated, expected);
        quizzes.markReady(quizId, validationStatus, validationWarnings);
    }

    @Transactional
    public void appendGroundedAndComplete(
            UUID quizId,
            List<QuizDtos.GroundedQuestion> generated,
            QuizDtos.QuestionCounts expected,
            long baseQuizVersion,
            long baseQuestionCount,
            String baseQuestionFingerprint) {
        questions.appendGrounded(
                quizId, generated, expected, baseQuizVersion,
                baseQuestionCount, baseQuestionFingerprint);
    }

    @Transactional
    public void appendGroundedAndComplete(
            UUID quizId,
            List<QuizDtos.GroundedQuestion> generated,
            QuizDtos.QuestionCounts expected,
            long baseQuizVersion,
            long baseQuestionCount,
            String baseQuestionFingerprint,
            AiValidationStatus validationStatus,
            List<QuizDtos.AiValidationWarning> validationWarnings) {
        questions.appendGrounded(
                quizId, generated, expected, baseQuizVersion,
                baseQuestionCount, baseQuestionFingerprint);
        quizzes.mergeAiValidation(quizId, validationStatus, validationWarnings);
    }
}
