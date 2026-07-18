package com.genquiz.bk.quiz;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import java.text.Normalizer;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class QuestionService {
    private final QuestionRepository questions;
    private final QuestionOptionRepository options;
    private final AcceptedAnswerRepository acceptedAnswers;
    private final QuizService quizzes;

    public QuestionService(QuestionRepository questions, QuestionOptionRepository options,
                           AcceptedAnswerRepository acceptedAnswers, QuizService quizzes) {
        this.questions = questions;
        this.options = options;
        this.acceptedAnswers = acceptedAnswers;
        this.quizzes = quizzes;
    }

    @Transactional(readOnly = true)
    public List<QuizDtos.QuestionResponse> listForOwner(UUID actorId, UUID quizId) {
        quizzes.getOwned(actorId, quizId);
        return questions.findByQuizIdOrderByPosition(quizId).stream().map(this::authorResponse).toList();
    }

    @Transactional
    public QuizDtos.QuestionResponse create(UUID actorId, UUID quizId, QuizDtos.QuestionRequest request) {
        Quiz quiz = quizzes.getOwned(actorId, quizId);
        requireEditable(quiz);
        validate(request);
        int position = Math.toIntExact(questions.countByQuizId(quizId));
        Question question = questions.save(new Question(quizId, request.sourceChunkId(), request.type(),
                request.prompt(), request.explanation(), request.points(), position, request.difficulty()));
        replaceAnswers(question, request);
        return authorResponse(question);
    }

    @Transactional
    public QuizDtos.QuestionResponse update(UUID actorId, UUID questionId, QuizDtos.QuestionRequest request) {
        Question question = require(questionId);
        Quiz quiz = quizzes.getOwned(actorId, question.getQuizId());
        requireEditable(quiz);
        validate(request);
        question.update(request.sourceChunkId(), request.type(), request.prompt(), request.explanation(),
                request.points(), request.difficulty());
        replaceAnswers(question, request);
        return authorResponse(question);
    }

    @Transactional
    public void delete(UUID actorId, UUID questionId) {
        Question question = require(questionId);
        requireEditable(quizzes.getOwned(actorId, question.getQuizId()));
        options.deleteByQuestionId(questionId);
        acceptedAnswers.deleteByQuestionId(questionId);
        questions.delete(question);
        normalizePositions(question.getQuizId());
    }

    @Transactional
    public List<QuizDtos.QuestionResponse> reorder(UUID actorId, UUID quizId, List<UUID> orderedIds) {
        requireEditable(quizzes.getOwned(actorId, quizId));
        List<Question> existing = questions.findByQuizIdOrderByPosition(quizId);
        if (orderedIds.size() != existing.size() || new HashSet<>(orderedIds).size() != orderedIds.size()
                || !new HashSet<>(orderedIds).equals(existing.stream().map(Question::getId).collect(java.util.stream.Collectors.toSet()))) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "Danh sách sắp xếp phải chứa đúng tất cả câu hỏi của bài kiểm tra");
        }
        var byId = existing.stream().collect(java.util.stream.Collectors.toMap(Question::getId, q -> q));
        for (int index = 0; index < orderedIds.size(); index++) byId.get(orderedIds.get(index)).moveTo(index);
        return orderedIds.stream().map(byId::get).map(this::authorResponse).toList();
    }

    @Transactional
    public void replaceGenerated(UUID quizId, List<QuizDtos.QuestionRequest> generated,
                                 QuizDtos.QuestionCounts expected) {
        validateGeneratedBatch(generated, expected);
        List<Question> old = questions.findByQuizIdOrderByPosition(quizId);
        List<UUID> oldIds = old.stream().map(Question::getId).toList();
        if (!oldIds.isEmpty()) {
            options.deleteByQuestionIdIn(oldIds);
            acceptedAnswers.deleteByQuestionIdIn(oldIds);
            questions.deleteAll(old);
        }
        for (int index = 0; index < generated.size(); index++) {
            QuizDtos.QuestionRequest request = generated.get(index);
            Question question = questions.save(new Question(quizId, request.sourceChunkId(), request.type(),
                    request.prompt(), request.explanation(), request.points(), index, request.difficulty()));
            replaceAnswers(question, request);
        }
    }

    private void replaceAnswers(Question question, QuizDtos.QuestionRequest request) {
        options.deleteByQuestionId(question.getId());
        acceptedAnswers.deleteByQuestionId(question.getId());
        if (request.type() == QuestionType.FILL_BLANK) {
            List<AcceptedAnswer> values = new ArrayList<>();
            for (int i = 0; i < request.acceptedAnswers().size(); i++) {
                values.add(new AcceptedAnswer(question.getId(), request.acceptedAnswers().get(i), i));
            }
            acceptedAnswers.saveAll(values);
        } else {
            List<QuestionOption> values = new ArrayList<>();
            for (int i = 0; i < request.options().size(); i++) {
                var input = request.options().get(i);
                values.add(new QuestionOption(question.getId(), input.text(), input.correct(), i));
            }
            options.saveAll(values);
        }
    }

    public static void validate(QuizDtos.QuestionRequest request) {
        if (request == null || request.type() == null || request.prompt() == null || request.prompt().isBlank()) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "Câu hỏi phải có loại và nội dung hợp lệ");
        }
        List<QuizDtos.OptionRequest> optionValues = request.options() == null ? List.of() : request.options();
        List<String> answerValues = request.acceptedAnswers() == null ? List.of() : request.acceptedAnswers();
        if (request.points() == null || request.points().signum() <= 0) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT, "Điểm câu hỏi phải lớn hơn 0");
        }
        if (request.type() == QuestionType.FILL_BLANK) {
            if (!optionValues.isEmpty() || answerValues.isEmpty()) {
                throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                        "Câu điền khuyết không có lựa chọn và phải có ít nhất một đáp án");
            }
            Set<String> normalized = new LinkedHashSet<>();
            answerValues.forEach(answer -> normalized.add(AcceptedAnswer.normalize(answer)));
            if (normalized.contains("") || normalized.size() != answerValues.size()) {
                throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT, "Đáp án điền khuyết bị trống hoặc trùng");
            }
            return;
        }
        if (optionValues.size() != 4 || !answerValues.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "Câu trắc nghiệm phải có đúng 4 lựa chọn và không có đáp án điền khuyết");
        }
        Set<String> distinct = new HashSet<>();
        if (optionValues.stream().anyMatch(option -> option == null || option.text() == null || option.text().isBlank())) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "Lựa chọn không được để trống");
        }
        optionValues.forEach(option -> distinct.add(option.text().trim().toLowerCase(Locale.ROOT)));
        if (distinct.size() != 4) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT, "Các lựa chọn không được trùng nhau");
        }
        long correct = optionValues.stream().filter(QuizDtos.OptionRequest::correct).count();
        if (request.type() == QuestionType.SINGLE_CHOICE && correct != 1) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "Câu một lựa chọn phải có đúng một đáp án đúng");
        }
        if (request.type() == QuestionType.MULTIPLE_SELECT && correct < 2) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "Câu nhiều lựa chọn phải có ít nhất hai đáp án đúng");
        }
    }

    public static void validateGeneratedBatch(List<QuizDtos.QuestionRequest> generated,
                                              QuizDtos.QuestionCounts expected) {
        if (generated == null || expected == null || expected.singleChoice() < 0
                || expected.multipleSelect() < 0 || expected.fillBlank() < 0) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "Danh sách câu hỏi sinh tự động không hợp lệ");
        }

        int singleChoice = 0;
        int multipleSelect = 0;
        int fillBlank = 0;
        Set<String> prompts = new HashSet<>();
        for (QuizDtos.QuestionRequest request : generated) {
            validate(request);
            String normalizedPrompt = Normalizer.normalize(request.prompt(), Normalizer.Form.NFKC)
                    .toLowerCase(Locale.ROOT)
                    .replaceAll("\\s+", " ")
                    .trim();
            if (!prompts.add(normalizedPrompt)) {
                throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                        "Danh sách sinh tự động chứa câu hỏi trùng nhau");
            }
            switch (request.type()) {
                case SINGLE_CHOICE -> singleChoice++;
                case MULTIPLE_SELECT -> multipleSelect++;
                case FILL_BLANK -> fillBlank++;
            }
        }

        if (generated.size() != expected.total() || singleChoice != expected.singleChoice()
                || multipleSelect != expected.multipleSelect() || fillBlank != expected.fillBlank()) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "Số lượng câu hỏi sinh tự động không đúng theo từng loại");
        }
    }

    private QuizDtos.QuestionResponse authorResponse(Question question) {
        var optionDtos = options.findByQuestionIdOrderByPosition(question.getId()).stream()
                .map(option -> new QuizDtos.OptionResponse(option.getId(), option.getOptionText(), option.isCorrect(),
                        option.getPosition())).toList();
        var answers = acceptedAnswers.findByQuestionIdOrderByPosition(question.getId()).stream()
                .map(AcceptedAnswer::getAnswerText).toList();
        return new QuizDtos.QuestionResponse(question.getId(), question.getQuizId(), question.getType(),
                question.getPrompt(), question.getExplanation(), question.getPoints(), question.getPosition(),
                question.getDifficulty(), question.getSourceChunkId(), optionDtos, answers, question.getVersion());
    }

    private Question require(UUID questionId) {
        return questions.findById(questionId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Không tìm thấy câu hỏi"));
    }

    private static void requireEditable(Quiz quiz) {
        if (quiz.getStatus() == QuizStatus.GENERATING || quiz.getStatus() == QuizStatus.PUBLISHED
                || quiz.getStatus() == QuizStatus.ARCHIVED) {
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                    "Không thể sửa câu hỏi ở trạng thái hiện tại của bài kiểm tra");
        }
    }

    private void normalizePositions(UUID quizId) {
        List<Question> remaining = questions.findByQuizIdOrderByPosition(quizId);
        for (int i = 0; i < remaining.size(); i++) remaining.get(i).moveTo(i);
    }
}
