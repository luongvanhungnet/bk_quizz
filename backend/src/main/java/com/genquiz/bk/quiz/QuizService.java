package com.genquiz.bk.quiz;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import com.genquiz.bk.job.Job;
import com.genquiz.bk.job.JobService;
import com.genquiz.bk.job.JobType;
import com.genquiz.bk.config.QuizGenerationBatchProperties;
import com.genquiz.bk.source.SourceDocument;
import com.genquiz.bk.source.SourceDocumentRepository;
import com.genquiz.bk.source.SourceStatus;
import com.genquiz.bk.topic.Topic;
import com.genquiz.bk.topic.TopicService;
import com.genquiz.bk.topic.Visibility;
import java.time.Clock;
import java.time.Instant;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import com.genquiz.bk.security.VerifiedAccountGuard;
import com.genquiz.bk.common.error.ApiException;

@Service
public class QuizService {
    private final QuizRepository quizzes;
    private final QuizSourceRepository quizSources;
    private final QuestionRepository questions;
    private final SourceDocumentRepository sources;
    private final TopicService topics;
    private final JobService jobs;
    private final ObjectMapper objectMapper;
    private final Clock clock;
    private final VerifiedAccountGuard verifiedAccounts;
    private final QuizGenerationBatchProperties batchProperties;

    @Autowired
    public QuizService(QuizRepository quizzes, QuizSourceRepository quizSources, QuestionRepository questions,
                       SourceDocumentRepository sources, TopicService topics, JobService jobs,
                       ObjectMapper objectMapper, VerifiedAccountGuard verifiedAccounts,
                       QuizGenerationBatchProperties batchProperties) {
        this(quizzes, quizSources, questions, sources, topics, jobs, objectMapper,
                verifiedAccounts, batchProperties, Clock.systemUTC());
    }

    QuizService(QuizRepository quizzes, QuizSourceRepository quizSources, QuestionRepository questions,
                SourceDocumentRepository sources, TopicService topics, JobService jobs,
                ObjectMapper objectMapper, VerifiedAccountGuard verifiedAccounts,
                QuizGenerationBatchProperties batchProperties, Clock clock) {
        this.quizzes = quizzes;
        this.quizSources = quizSources;
        this.questions = questions;
        this.sources = sources;
        this.topics = topics;
        this.jobs = jobs;
        this.objectMapper = objectMapper;
        this.verifiedAccounts = verifiedAccounts;
        this.batchProperties = batchProperties;
        this.clock = clock;
    }

    @Transactional
    public Quiz createManual(UUID actorId, QuizDtos.SaveRequest request) {
        topics.getOwned(actorId, request.topicId());
        Quiz quiz = Quiz.manual(request.topicId(), actorId, request.title(), request.description(),
                request.difficulty(), request.durationMinutes(), request.visibility());
        quiz.setCognitiveMode(request.resolvedCognitiveMode());
        return quizzes.save(quiz);
    }

    @Transactional(readOnly = true)
    public Page<Quiz> listOwned(UUID actorId, Pageable pageable) {
        return quizzes.findByOwnerIdAndDeletedAtIsNull(actorId, pageable);
    }

    @Transactional(readOnly = true)
    public Page<Quiz> listOwnedByTopic(UUID actorId, UUID topicId, Pageable pageable) {
        topics.getOwned(actorId, topicId);
        return quizzes.findByTopicIdAndOwnerIdAndDeletedAtIsNull(topicId, actorId, pageable);
    }

    @Transactional(readOnly = true)
    public Quiz getOwned(UUID actorId, UUID quizId) {
        Quiz quiz = requireActive(quizId);
        if (!quiz.isOwnedBy(actorId)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Bạn không có quyền chỉnh sửa bài kiểm tra này");
        }
        return quiz;
    }

    @Transactional(readOnly = true)
    public List<SourceDocument> listSources(UUID actorId, UUID quizId) {
        getOwned(actorId, quizId);
        return sources.findAllById(quizSources.findByQuizId(quizId).stream()
                .map(QuizSource::getSourceDocumentId).toList());
    }

    @Transactional(readOnly = true)
    public Quiz getAccessible(UUID actorId, UUID quizId) {
        Quiz quiz = requireActive(quizId);
        if (quiz.isOwnedBy(actorId)) return quiz;
        if (quiz.getStatus() != QuizStatus.PUBLISHED || quiz.getVisibility() != Visibility.PUBLIC) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Bạn không có quyền xem bài kiểm tra này");
        }
        topics.getAccessible(actorId, quiz.getTopicId());
        return quiz;
    }

    @Transactional
    public Quiz update(UUID actorId, UUID quizId, QuizDtos.SaveRequest request) {
        Quiz quiz = getOwned(actorId, quizId);
        if (!quiz.getTopicId().equals(request.topicId())) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT, "Không thể chuyển bài kiểm tra sang chủ đề khác");
        }
        quiz.update(request.title(), request.description(), request.difficulty(), request.durationMinutes(),
                request.visibility());
        quiz.setCognitiveMode(request.resolvedCognitiveMode());
        return quiz;
    }

    @Transactional
    public Quiz publish(UUID actorId, UUID quizId) {
        verifiedAccounts.require(actorId);
        Quiz quiz = getOwned(actorId, quizId);
        topics.getOwned(actorId, quiz.getTopicId());
        if (questions.countByQuizId(quizId) == 0) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "Bài kiểm tra phải có ít nhất một câu hỏi");
        }
        try {
            quiz.publish(Instant.now(clock));
        } catch (IllegalStateException exception) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, exception.getMessage());
        }
        return quiz;
    }

    @Transactional(readOnly = true)
    public Quiz getForAttempt(UUID actorId, UUID quizId, boolean assignmentAccessGranted) {
        Quiz quiz = requireActive(quizId);
        if (quiz.getStatus() != QuizStatus.PUBLISHED) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Bài kiểm tra chưa được xuất bản");
        }
        if (assignmentAccessGranted || quiz.isOwnedBy(actorId)) return quiz;
        return getAccessible(actorId, quizId);
    }

    @Transactional
    public GenerationResult generate(UUID actorId, QuizDtos.GenerateRequest request, String idempotencyKey) {
        validateGeneration(actorId, request);
        Quiz quiz = Quiz.generated(request.topicId(), actorId, request.title(), request.difficulty(),
                request.durationMinutes(), request.visibility());
        quiz.setCognitiveMode(request.resolvedCognitiveMode());
        quizzes.save(quiz);
        quizSources.saveAll(request.sourceIds().stream().distinct()
                .map(sourceId -> new QuizSource(quiz.getId(), sourceId)).toList());
        String scopedKey = idempotencyKey == null || idempotencyKey.isBlank()
                ? null : "quiz-generation:" + actorId + ":" + idempotencyKey;
        Job job = jobs.enqueue(JobType.QUIZ_GENERATION, actorId, quiz.getId(), generationPayload(quiz, request),
                scopedKey, maxJobAttempts(request.questionCounts()));
        if (!quiz.getId().equals(job.getResourceId())) {
            quizSources.deleteByQuizId(quiz.getId());
            quizzes.delete(quiz);
            Quiz existing = requireActive(job.getResourceId());
            return new GenerationResult(existing, job);
        }
        return new GenerationResult(quiz, job);
    }

    @Transactional
    public GenerationResult appendGeneration(
            UUID actorId,
            UUID quizId,
            QuizDtos.AppendGenerateRequest request,
            String idempotencyKey) {
        Quiz quiz = getOwnedForGeneration(actorId, quizId);
        if (quiz.getStatus() != QuizStatus.DRAFT
                && quiz.getStatus() != QuizStatus.READY) {
            throw new ApiException(
                    HttpStatus.CONFLICT,
                    "QUIZ_APPEND_NOT_ALLOWED",
                    "Chỉ có thể sinh thêm câu hỏi cho Quiz bản nháp hoặc sẵn sàng.");
        }
        if (jobs.hasActiveQuizGeneration(quizId)) {
            throw new ApiException(
                    HttpStatus.CONFLICT,
                    "QUIZ_GENERATION_IN_PROGRESS",
                    "Quiz đang có một tác vụ sinh câu hỏi khác.");
        }
        List<Question> existing =
                questions.findByQuizIdOrderByPosition(quizId);
        int requested = request.questionCounts().total();
        if (requested < 1
                || existing.size() + requested > QuizLimits.MAX_QUESTIONS_PER_QUIZ) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_CONTENT,
                    "QUIZ_QUESTION_LIMIT_EXCEEDED",
                    "Tổng số câu hỏi của Quiz không được vượt quá "
                            + QuizLimits.MAX_QUESTIONS_PER_QUIZ + ".");
        }
        validateGenerationSources(
                actorId, quiz.getTopicId(), request.sourceIds());

        var linkedSources = quizSources.findByQuizId(quizId).stream()
                .map(QuizSource::getSourceDocumentId)
                .collect(java.util.stream.Collectors.toCollection(
                        LinkedHashSet::new));
        List<UUID> missingSourceIds = request.sourceIds().stream()
                .filter(sourceId -> !linkedSources.contains(sourceId))
                .toList();
        quizSources.saveAll(missingSourceIds.stream()
                .map(sourceId -> new QuizSource(quizId, sourceId)).toList());

        String scopedKey = idempotencyKey == null || idempotencyKey.isBlank()
                ? null
                : "quiz-generation-append:" + actorId + ":" + quizId + ":"
                        + idempotencyKey;
        Job job = jobs.enqueue(
                JobType.QUIZ_GENERATION,
                actorId,
                quizId,
                appendGenerationPayload(quiz, request, existing),
                scopedKey,
                maxJobAttempts(request.questionCounts()));
        return new GenerationResult(quiz, job);
    }

    void requireNoActiveQuestionGeneration(UUID quizId) {
        if (jobs.hasActiveQuizGeneration(quizId)) {
            throw new ApiException(
                    HttpStatus.CONFLICT,
                    "QUIZ_GENERATION_IN_PROGRESS",
                    "Không thể sửa câu hỏi khi Quiz đang được sinh thêm bằng AI.");
        }
    }

    @Transactional
    public GenerationResult retry(UUID actorId, UUID quizId, QuizDtos.GenerateRequest request,
                                  String idempotencyKey) {
        Quiz quiz = getOwned(actorId, quizId);
        if (!quiz.getTopicId().equals(request.topicId()) || quiz.getStatus() != QuizStatus.FAILED
                || quiz.getGenerationMode() != GenerationMode.AI) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Bài kiểm tra không thể thử sinh lại");
        }
        validateGeneration(actorId, request);
        quiz.queueRetry();
        quiz.setCognitiveMode(request.resolvedCognitiveMode());
        quizSources.deleteByQuizId(quizId);
        quizSources.saveAll(request.sourceIds().stream().distinct()
                .map(sourceId -> new QuizSource(quizId, sourceId)).toList());
        String key = idempotencyKey == null || idempotencyKey.isBlank() ? null
                : "quiz-generation-retry:" + actorId + ":" + quizId + ":" + idempotencyKey;
        Job job = jobs.enqueue(JobType.QUIZ_GENERATION, actorId, quizId,
                generationPayload(quiz, request), key, maxJobAttempts(request.questionCounts()));
        return new GenerationResult(quiz, job);
    }

    @Transactional
    public GenerationResult retryLast(UUID actorId, UUID quizId) {
        Quiz quiz = getOwned(actorId, quizId);
        Job latest = jobs.latestOwnedQuizGeneration(actorId, quizId);
        boolean append = QuizGenerationOperation.fromPayload(
                latest.getPayload()) == QuizGenerationOperation.APPEND;
        if ((!append && (quiz.getStatus() != QuizStatus.FAILED
                || quiz.getGenerationMode() != GenerationMode.AI))
                || (append && quiz.getStatus() != QuizStatus.DRAFT
                && quiz.getStatus() != QuizStatus.READY)) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT, "Bài kiểm tra không thể thử sinh lại");
        }
        Job job = jobs.retryOwnedQuizGeneration(actorId, quizId);
        if (!append) quiz.queueRetry();
        return new GenerationResult(quiz, job);
    }

    @Transactional
    public void markGenerating(UUID quizId) {
        try {
            Quiz quiz = requireActive(quizId);
            if (quiz.getStatus() != QuizStatus.GENERATING) quiz.markGenerating();
        } catch (IllegalStateException exception) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, exception.getMessage());
        }
    }

    @Transactional
    public void markReady(UUID quizId) {
        if (questions.countByQuizId(quizId) == 0) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT, "AI không tạo được câu hỏi hợp lệ");
        }
        requireActive(quizId).markReady();
    }

    @Transactional
    public void markReady(UUID quizId, AiValidationStatus validationStatus,
                          List<QuizDtos.AiValidationWarning> validationWarnings) {
        if (questions.countByQuizId(quizId) == 0) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "AI không tạo được câu hỏi có thể sử dụng");
        }
        requireActive(quizId).markReady(validationStatus, validationWarnings);
    }

    @Transactional
    public void mergeAiValidation(UUID quizId, AiValidationStatus validationStatus,
                                  List<QuizDtos.AiValidationWarning> validationWarnings) {
        requireActive(quizId).mergeAiValidation(validationStatus, validationWarnings);
    }

    @Transactional
    public void refreshAiValidationStatus(UUID quizId) {
        List<Question> values = questions.findByQuizIdOrderByPosition(quizId);
        AiValidationStatus status = values.stream().anyMatch(
                question -> question.getAiValidationStatus() == AiValidationStatus.WARNING)
                ? AiValidationStatus.WARNING
                : values.stream().anyMatch(
                        question -> question.getAiValidationStatus() == AiValidationStatus.REVIEWED)
                        ? AiValidationStatus.REVIEWED : AiValidationStatus.VERIFIED;
        requireActive(quizId).updateAiValidationStatus(status);
    }

    @Transactional
    public void markFailed(UUID quizId, String safeCode, String safeMessage) {
        requireActive(quizId).markFailed(safeCode, safeMessage);
    }

    @Transactional
    public void delete(UUID actorId, UUID quizId) {
        getOwned(actorId, quizId).softDelete();
    }

    @Transactional(readOnly = true)
    public long questionCount(UUID quizId) { return questions.countByQuizId(quizId); }

    @Transactional(readOnly = true)
    public Quiz requireForJob(UUID quizId) { return requireActive(quizId); }

    @Transactional
    public Quiz lockForGenerationCommit(UUID quizId) {
        return quizzes.findLockedActiveById(quizId)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Không tìm thấy bài kiểm tra"));
    }

    private void validateGeneration(UUID actorId, QuizDtos.GenerateRequest request) {
        topics.getOwned(actorId, request.topicId());
        int total = request.questionCounts().total();
        if (total < 1 || total > QuizLimits.MAX_QUESTIONS_PER_QUIZ) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "Tổng số câu hỏi phải từ 1 đến "
                            + QuizLimits.MAX_QUESTIONS_PER_QUIZ);
        }
        validateGenerationSources(actorId, request.topicId(), request.sourceIds());
    }

    private void validateGenerationSources(
            UUID actorId, UUID topicId, List<UUID> sourceIds) {
        var uniqueSourceIds = new LinkedHashSet<>(sourceIds);
        if (uniqueSourceIds.size() != sourceIds.size()) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT, "Danh sách tài liệu bị trùng");
        }
        List<SourceDocument> ready = sources.findAllByIdInAndOwnerIdAndStatusAndDeletedAtIsNull(
                uniqueSourceIds, actorId, SourceStatus.READY);
        if (ready.size() != uniqueSourceIds.size()
                || ready.stream().anyMatch(source -> !source.getTopicId().equals(topicId))) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "Tất cả tài liệu phải thuộc chủ đề và đã xử lý xong");
        }
    }

    private String generationPayload(Quiz quiz, QuizDtos.GenerateRequest request) {
        try {
            return objectMapper.writeValueAsString(Map.of(
                    "operation", QuizGenerationOperation.CREATE,
                    "quizId", quiz.getId(),
                    "topicId", quiz.getTopicId(),
                    "title", request.title(),
                    "sourceIds", request.sourceIds(),
                    "difficulty", quiz.getDifficulty(),
                    "cognitiveMode", request.resolvedCognitiveMode(),
                    "questionCounts", request.questionCounts()));
        } catch (JacksonException exception) {
            throw new IllegalStateException("Không thể tạo payload sinh câu hỏi", exception);
        }
    }

    private String appendGenerationPayload(
            Quiz quiz,
            QuizDtos.AppendGenerateRequest request,
            List<Question> existing) {
        try {
            var payload = new java.util.LinkedHashMap<String, Object>();
            payload.put("operation", QuizGenerationOperation.APPEND);
            payload.put("quizId", quiz.getId());
            payload.put("topicId", quiz.getTopicId());
            payload.put("title", quiz.getTitle());
            payload.put("sourceIds", request.sourceIds());
            payload.put(
                    "difficulty",
                    quiz.getDifficulty() == null
                            ? Difficulty.MEDIUM : quiz.getDifficulty());
            payload.put("cognitiveMode", request.cognitiveMode());
            payload.put("questionCounts", request.questionCounts());
            payload.put("baseQuizVersion", quiz.getVersion());
            payload.put("baseQuestionCount", existing.size());
            payload.put(
                    "baseQuestionFingerprint",
                    QuestionService.questionFingerprint(existing));
            payload.put(
                    "existingPrompts",
                    existing.stream()
                            .map(Question::getPrompt)
                            .map(value -> value.substring(
                                    0, Math.min(500, value.length())))
                            .toList());
            return objectMapper.writeValueAsString(payload);
        } catch (JacksonException exception) {
            throw new IllegalStateException(
                    "KhÃ´ng thá»ƒ táº¡o payload sinh ná»‘i cÃ¢u há»i",
                    exception);
        }
    }

    private int maxJobAttempts(QuizDtos.QuestionCounts counts) {
        int batches = (counts.total() + batchProperties.batchMaxQuestions() - 1)
                / batchProperties.batchMaxQuestions();
        return batches * batchProperties.batchMaxAttempts();
    }

    private Quiz requireActive(UUID quizId) {
        return quizzes.findByIdAndDeletedAtIsNull(quizId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Không tìm thấy bài kiểm tra"));
    }

    private Quiz getOwnedForGeneration(UUID actorId, UUID quizId) {
        Quiz quiz = quizzes.findLockedActiveById(quizId)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Không tìm thấy bài kiểm tra"));
        if (!quiz.isOwnedBy(actorId)) {
            throw new ResponseStatusException(
                    HttpStatus.FORBIDDEN,
                    "Bạn không có quyền chỉnh sửa bài kiểm tra này");
        }
        return quiz;
    }

    public record GenerationResult(Quiz quiz, Job job) {}
}
