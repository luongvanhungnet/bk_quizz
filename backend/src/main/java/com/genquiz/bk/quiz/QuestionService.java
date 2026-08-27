package com.genquiz.bk.quiz;

import com.genquiz.bk.common.error.ApiException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.text.Normalizer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.springframework.http.HttpStatus;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class QuestionService {
    private static final int POSITION_COMPACTION_OFFSET = 1000;
    private final QuestionRepository questions;
    private final QuestionOptionRepository options;
    private final AcceptedAnswerRepository acceptedAnswers;
    private final QuizService quizzes;
    private final QuestionCitationRepository citations;
    private final com.genquiz.bk.source.SourceChunkRepository sourceChunks;
    private final com.genquiz.bk.source.SourceDocumentRepository sourceDocuments;
    private final QuizSourceRepository quizSources;

    @Autowired
    public QuestionService(QuestionRepository questions, QuestionOptionRepository options,
                           AcceptedAnswerRepository acceptedAnswers, QuizService quizzes,
                           QuestionCitationRepository citations,
                           com.genquiz.bk.source.SourceChunkRepository sourceChunks,
                           com.genquiz.bk.source.SourceDocumentRepository sourceDocuments,
                           QuizSourceRepository quizSources) {
        this.questions = questions;
        this.options = options;
        this.acceptedAnswers = acceptedAnswers;
        this.quizzes = quizzes;
        this.citations = citations; this.sourceChunks = sourceChunks; this.sourceDocuments = sourceDocuments;
        this.quizSources = quizSources;
    }

    QuestionService(QuestionRepository questions, QuestionOptionRepository options,
                    AcceptedAnswerRepository acceptedAnswers, QuizService quizzes) {
        this(questions, options, acceptedAnswers, quizzes, null, null, null, null);
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
        quizzes.requireNoActiveQuestionGeneration(quizId);
        long currentCount = questions.countByQuizId(quizId);
        if (currentCount >= QuizLimits.MAX_QUESTIONS_PER_QUIZ) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_CONTENT,
                    "QUIZ_QUESTION_LIMIT_EXCEEDED",
                    "Quiz đã đạt giới hạn "
                            + QuizLimits.MAX_QUESTIONS_PER_QUIZ + " câu hỏi.");
        }
        validate(request);
        int position = Math.toIntExact(currentCount);
        Question question = questions.save(newQuestion(quizId, request.sourceChunkId(), request, position));
        replaceAnswers(question, request);
        if (citations != null) citations.deleteByQuestionId(question.getId());
        return authorResponse(question);
    }

    @Transactional
    public QuizDtos.QuestionImportResponse importQuestions(
            UUID actorId, UUID quizId, List<QuestionExcelWorkbook.ParsedQuestion> imported) {
        Quiz quiz = quizzes.getOwned(actorId, quizId);
        requireEditable(quiz);
        quizzes.requireNoActiveQuestionGeneration(quizId);
        List<Question> existing = questions.findByQuizIdOrderByPosition(quizId);
        List<com.genquiz.bk.common.api.ApiFieldError> errors = new ArrayList<>();
        if (imported == null || imported.isEmpty()) {
            errors.add(new com.genquiz.bk.common.api.ApiFieldError(
                    "QUESTION_IMPORT_EMPTY", "CauHoi", "File chưa có câu hỏi để import."));
        } else if (existing.size() + imported.size()
                > QuizLimits.MAX_QUESTIONS_PER_QUIZ) {
            errors.add(new com.genquiz.bk.common.api.ApiFieldError(
                    "QUIZ_QUESTION_LIMIT_EXCEEDED", "CauHoi",
                    "Quiz hiện có " + existing.size() + " câu; chỉ có thể import thêm "
                            + Math.max(0, QuizLimits.MAX_QUESTIONS_PER_QUIZ
                                    - existing.size()) + " câu."));
        }
        Set<String> prompts = existing.stream().map(Question::getPrompt)
                .map(QuestionService::normalizePrompt).collect(java.util.stream.Collectors.toSet());
        if (imported != null) {
            for (QuestionExcelWorkbook.ParsedQuestion row : imported) {
                try {
                    validate(row.question());
                } catch (ResponseStatusException exception) {
                    errors.add(new com.genquiz.bk.common.api.ApiFieldError(
                            "QUESTION_ROW_INVALID", "CauHoi!" + row.excelRowNumber(),
                            "Hàng " + row.excelRowNumber() + ": " + exception.getReason()));
                }
                if (!prompts.add(normalizePrompt(row.question().prompt()))) {
                    errors.add(new com.genquiz.bk.common.api.ApiFieldError(
                            "DUPLICATE_QUESTION", "CauHoi!B" + row.excelRowNumber(),
                            "Hàng " + row.excelRowNumber()
                                    + " – Nội dung: Câu hỏi đã tồn tại trong Quiz hoặc bị trùng trong file."));
                }
            }
        }
        if (!errors.isEmpty()) {
            throw new ApiException(HttpStatus.UNPROCESSABLE_CONTENT, "QUESTION_IMPORT_INVALID",
                    "File Excel có dữ liệu không hợp lệ.", errors.stream().limit(200).toList());
        }
        int position = existing.size();
        for (QuestionExcelWorkbook.ParsedQuestion row : imported) {
            QuizDtos.QuestionRequest request = row.question();
            Question question = questions.save(newQuestion(quizId, null, request, position++));
            replaceAnswers(question, request);
        }
        quizzes.refreshAiValidationStatus(quizId);
        return new QuizDtos.QuestionImportResponse(imported.size(), existing.size() + imported.size());
    }

    @Transactional
    public QuizDtos.QuestionResponse update(UUID actorId, UUID questionId, QuizDtos.QuestionRequest request) {
        Question question = require(questionId);
        Quiz quiz = quizzes.getOwned(actorId, question.getQuizId());
        requireEditable(quiz);
        quizzes.requireNoActiveQuestionGeneration(question.getQuizId());
        validate(request);
        question.update(null, request.type(), request.prompt(), request.explanation(),
                request.points(), request.difficulty());
        applyCognitive(question, request);
        clearExistingAnswers(question.getId());
        replaceAnswers(question, request);
        if (citations != null) citations.deleteByQuestionId(question.getId());
        quizzes.refreshAiValidationStatus(question.getQuizId());
        return authorResponse(question);
    }

    @Transactional
    public void delete(UUID actorId, UUID questionId) {
        Question question = require(questionId);
        requireEditable(quizzes.getOwned(actorId, question.getQuizId()));
        quizzes.requireNoActiveQuestionGeneration(question.getQuizId());
        try {
            options.deleteByQuestionId(questionId);
            acceptedAnswers.deleteByQuestionId(questionId);
            if (citations != null) citations.deleteByQuestionId(questionId);
            questions.delete(question);
            questions.flush();
            questions.movePositionsAfterToTemporaryRange(
                    question.getQuizId(), question.getPosition(), POSITION_COMPACTION_OFFSET);
            questions.restoreTemporaryPositionsAfterDelete(
                    question.getQuizId(), POSITION_COMPACTION_OFFSET);
            quizzes.refreshAiValidationStatus(question.getQuizId());
        } catch (DataIntegrityViolationException exception) {
            throw new ApiException(
                    HttpStatus.CONFLICT,
                    "QUESTION_DELETE_FAILED",
                    "Không thể xóa câu hỏi do ràng buộc dữ liệu. Vui lòng tải lại Quiz và thử lại.");
        }
    }

    @Transactional
    public QuizDtos.QuestionResponse reviewValidation(UUID actorId, boolean admin,
                                                       UUID questionId, String note) {
        Question question = require(questionId);
        if (admin) quizzes.requireForJob(question.getQuizId());
        else quizzes.getOwned(actorId, question.getQuizId());
        try {
            question.markValidationReviewed(actorId, note, java.time.Instant.now());
        } catch (IllegalStateException exception) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, exception.getMessage());
        }
        quizzes.refreshAiValidationStatus(question.getQuizId());
        return authorResponse(question);
    }

    @Transactional
    public QuizDtos.QuestionResponse undoValidationReview(UUID actorId, boolean admin,
                                                           UUID questionId) {
        Question question = require(questionId);
        if (admin) quizzes.requireForJob(question.getQuizId());
        else quizzes.getOwned(actorId, question.getQuizId());
        try {
            question.undoValidationReview();
        } catch (IllegalStateException exception) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, exception.getMessage());
        }
        quizzes.refreshAiValidationStatus(question.getQuizId());
        return authorResponse(question);
    }

    @Transactional
    public List<QuizDtos.QuestionResponse> reorder(UUID actorId, UUID quizId, List<UUID> orderedIds) {
        requireEditable(quizzes.getOwned(actorId, quizId));
        quizzes.requireNoActiveQuestionGeneration(quizId);
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
            if (citations != null) citations.deleteByQuestionIdIn(oldIds);
            questions.deleteAll(old);
        }
        for (int index = 0; index < generated.size(); index++) {
            QuizDtos.QuestionRequest request = generated.get(index);
            Question question = questions.save(newQuestion(quizId, request.sourceChunkId(), request, index));
            replaceAnswers(question, request);
        }
    }

    @Transactional
    public void replaceGrounded(UUID quizId, List<QuizDtos.GroundedQuestion> generated,
                                 QuizDtos.QuestionCounts expected) {
        validateUsableGeneratedBatch(
                generated.stream().map(QuizDtos.GroundedQuestion::question).toList());
        generated = resolveGroundedCitations(quizId, generated);
        List<Question> old = questions.findByQuizIdOrderByPosition(quizId);
        List<UUID> oldIds = old.stream().map(Question::getId).toList();
        if (!oldIds.isEmpty()) {
            options.deleteByQuestionIdIn(oldIds); acceptedAnswers.deleteByQuestionIdIn(oldIds);
            citations.deleteByQuestionIdIn(oldIds); questions.deleteAll(old);
        }
        for (int index = 0; index < generated.size(); index++) {
            var item = generated.get(index); var request = item.question();
            List<QuizDtos.CitationRequest> itemCitations = safeCitations(item);
            UUID primary = itemCitations.isEmpty() ? null
                    : itemCitations.get(0).sourceChunkId();
            Question question = newQuestion(quizId, primary, request, index);
            question.applyAiValidation(item.validationStatus(), item.validationWarnings());
            question = questions.save(question);
            replaceAnswers(question, request);
            List<QuestionCitation> values = new ArrayList<>();
            java.util.Map<CitationRole, Integer> positions = new java.util.EnumMap<>(CitationRole.class);
            for (var citation : itemCitations) {
                int position = positions.merge(citation.role(), 1, Integer::sum) - 1;
                values.add(new QuestionCitation(question.getId(), citation.sourceChunkId(), citation.role(),
                        citation.evidenceQuote(), position));
            }
            citations.saveAll(values);
        }
    }

    @Transactional
    public void appendGrounded(
            UUID quizId,
            List<QuizDtos.GroundedQuestion> generated,
            QuizDtos.QuestionCounts expected,
            long baseQuizVersion,
            long baseQuestionCount,
            String baseQuestionFingerprint) {
        validateUsableGeneratedBatch(
                generated.stream().map(QuizDtos.GroundedQuestion::question).toList());
        Quiz quiz = quizzes.lockForGenerationCommit(quizId);
        List<Question> existing = questions.findByQuizIdOrderByPosition(quizId);
        if (quiz.getVersion() != baseQuizVersion
                || existing.size() != baseQuestionCount
                || !questionFingerprint(existing).equals(baseQuestionFingerprint)) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT, "QUIZ_CHANGED_DURING_GENERATION");
        }
        if (existing.size() + generated.size()
                > QuizLimits.MAX_QUESTIONS_PER_QUIZ) {
            throw new ResponseStatusException(
                    HttpStatus.UNPROCESSABLE_CONTENT, "QUIZ_QUESTION_LIMIT_EXCEEDED");
        }
        generated = resolveGroundedCitations(quizId, generated);
        int startPosition = existing.size();
        for (int index = 0; index < generated.size(); index++) {
            var item = generated.get(index);
            var request = item.question();
            List<QuizDtos.CitationRequest> itemCitations = safeCitations(item);
            UUID primary = itemCitations.isEmpty() ? null
                    : itemCitations.get(0).sourceChunkId();
            Question question = newQuestion(
                    quizId, primary, request, startPosition + index);
            question.applyAiValidation(item.validationStatus(), item.validationWarnings());
            question = questions.save(question);
            replaceAnswers(question, request);
            saveCitations(question, itemCitations);
        }
    }

    @Transactional(readOnly = true)
    public String questionFingerprint(UUID quizId) {
        return questionFingerprint(questions.findByQuizIdOrderByPosition(quizId));
    }

    static String questionFingerprint(List<Question> values) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            for (Question question : values) {
                digest.update(Integer.toString(question.getPosition())
                        .getBytes(StandardCharsets.UTF_8));
                digest.update((byte) 0);
                digest.update(normalizePrompt(question.getPrompt())
                        .getBytes(StandardCharsets.UTF_8));
                digest.update((byte) 0xff);
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (java.security.NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }

    private List<QuizDtos.GroundedQuestion> resolveGroundedCitations(
            UUID quizId, List<QuizDtos.GroundedQuestion> generated) {
        Set<UUID> allowedSources = quizSources.findByQuizId(quizId).stream()
                .map(QuizSource::getSourceDocumentId)
                .collect(java.util.stream.Collectors.toSet());
        java.util.Map<UUID, com.genquiz.bk.source.SourceDocument> allowedDocumentsByRagId =
                allowedSources.stream()
                        .map(sourceDocuments::findByIdAndDeletedAtIsNull)
                        .flatMap(Optional::stream)
                        .filter(document -> document.getRagDocumentId() != null)
                        .collect(java.util.stream.Collectors.toMap(
                                com.genquiz.bk.source.SourceDocument::getRagDocumentId,
                                document -> document));
        List<com.genquiz.bk.source.SourceChunk> allowedChunks = new ArrayList<>(allowedSources.stream()
                .flatMap(sourceId -> sourceChunks
                        .findBySourceDocumentIdOrderByChunkIndex(sourceId).stream())
                .toList());
        java.util.Map<UUID, com.genquiz.bk.source.SourceChunk> allowedById =
                new java.util.HashMap<>(allowedChunks.stream().collect(java.util.stream.Collectors.toMap(
                        com.genquiz.bk.source.SourceChunk::getId,
                        chunk -> chunk,
                        (first, ignored) -> first)));

        List<QuizDtos.GroundedQuestion> resolved = new ArrayList<>();
        for (var item : generated) {
            List<QuizDtos.CitationRequest> valid = new ArrayList<>();
            List<QuizDtos.AiValidationWarning> warnings = new ArrayList<>(
                    item.validationWarnings() == null
                            ? List.of() : item.validationWarnings());
            for (var citation : safeCitations(item)) {
                com.genquiz.bk.source.SourceChunk synchronizedChunk = syncCitationSnapshot(
                        citation, allowedDocumentsByRagId, allowedSources);
                if (synchronizedChunk != null) {
                    allowedById.entrySet().removeIf(entry ->
                            entry.getValue().getSourceDocumentId().equals(
                                    synchronizedChunk.getSourceDocumentId())
                                    && entry.getValue().getChunkIndex()
                                    == synchronizedChunk.getChunkIndex());
                    allowedById.put(synchronizedChunk.getId(), synchronizedChunk);
                    allowedChunks.removeIf(chunk ->
                            chunk.getSourceDocumentId().equals(
                                    synchronizedChunk.getSourceDocumentId())
                                    && chunk.getChunkIndex()
                                    == synchronizedChunk.getChunkIndex());
                    allowedChunks.add(synchronizedChunk);
                }
                com.genquiz.bk.source.SourceChunk exact =
                        citation.sourceChunkId() == null
                                ? null : allowedById.get(citation.sourceChunkId());
                if (exact == null && citation.sourceChunkId() != null) {
                    var referenced = sourceChunks.findById(citation.sourceChunkId());
                    if (referenced.isPresent()
                            && !allowedSources.contains(
                            referenced.get().getSourceDocumentId())) {
                        throw invalidCitation();
                    }
                }
                if (exact != null
                        && containsNormalized(
                        exact.getContent(), citation.evidenceQuote())) {
                    valid.add(citation);
                    continue;
                }
                List<com.genquiz.bk.source.SourceChunk> matches = allowedChunks.stream()
                        .filter(chunk -> containsNormalized(
                                chunk.getContent(), citation.evidenceQuote()))
                        .toList();
                if (matches.size() == 1) {
                    valid.add(new QuizDtos.CitationRequest(
                            matches.get(0).getId(), citation.role(),
                            citation.evidenceQuote()));
                    continue;
                }
                warnings.add(new QuizDtos.AiValidationWarning(
                        "INVALID_CITATION_QUOTE",
                        citation.role() == null ? null : citation.role().name(),
                        "Citation thuộc nguồn đã chọn và khớp nội dung đã đồng bộ",
                        citation.sourceChunkId() == null
                                ? null : citation.sourceChunkId().toString(),
                        citation.sourceChunkId() == null
                                ? null : citation.sourceChunkId().toString(),
                        "Không thể đối chiếu chắc chắn trích dẫn; câu hỏi vẫn được lưu để chủ Quiz kiểm tra."));
            }
            resolved.add(new QuizDtos.GroundedQuestion(
                    item.question(),
                    List.copyOf(valid),
                    warnings.isEmpty() && item.validationStatus() != AiValidationStatus.WARNING
                            ? AiValidationStatus.VERIFIED : AiValidationStatus.WARNING,
                    List.copyOf(warnings)));
        }
        return List.copyOf(resolved);
    }

    private com.genquiz.bk.source.SourceChunk syncCitationSnapshot(
            QuizDtos.CitationRequest citation,
            java.util.Map<UUID, com.genquiz.bk.source.SourceDocument> allowedDocumentsByRagId,
            Set<UUID> allowedSources) {
        if (citation.ragDocumentId() == null || citation.chunkText() == null
                || citation.chunkText().isBlank() || citation.sourceChunkId() == null) {
            return null;
        }
        var source = allowedDocumentsByRagId.get(citation.ragDocumentId());
        if (source == null || !allowedSources.contains(source.getId())) {
            throw invalidCitation();
        }
        if (!containsNormalized(citation.chunkText(), citation.evidenceQuote())) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "QUIZ_CITATION_SNAPSHOT_INVALID");
        }
        var existing = sourceChunks.findById(citation.sourceChunkId()).orElse(null);
        if (existing != null && !existing.getSourceDocumentId().equals(source.getId())) {
            throw invalidCitation();
        }
        sourceChunks.deactivateActiveAtIndex(source.getId(), citation.chunkIndex());
        int tokenCount = Math.max(1, citation.chunkText().trim().split("\\s+").length);
        if (existing == null) {
            existing = new com.genquiz.bk.source.SourceChunk(
                    citation.sourceChunkId(), source.getId(), source.getTopicId(),
                    citation.chunkIndex(), citation.chunkText(), tokenCount,
                    citation.pageNumber(), citation.slideNumber(), citation.heading(),
                    citation.rawText(), citation.mathEnhanced(), citation.snapshotFingerprint());
        } else {
            existing.refreshSnapshot(citation.chunkIndex(), citation.chunkText(), tokenCount,
                    citation.pageNumber(), citation.slideNumber(), citation.heading(),
                    citation.rawText(), citation.mathEnhanced(), citation.snapshotFingerprint());
        }
        return sourceChunks.save(existing);
    }

    private void saveCitations(
            Question question, List<QuizDtos.CitationRequest> requested) {
        List<QuestionCitation> values = new ArrayList<>();
        java.util.Map<CitationRole, Integer> positions =
                new java.util.EnumMap<>(CitationRole.class);
        for (var citation : requested) {
            int position = positions.merge(citation.role(), 1, Integer::sum) - 1;
            values.add(new QuestionCitation(
                    question.getId(), citation.sourceChunkId(), citation.role(),
                    citation.evidenceQuote(), position));
        }
        citations.saveAll(values);
    }

    private static ResponseStatusException invalidCitation() {
        return new ResponseStatusException(
                HttpStatus.UNPROCESSABLE_CONTENT,
                "QUIZ_CITATION_SOURCE_FORBIDDEN");
    }

    private static boolean containsNormalized(String text, String quote) {
        String normalizedText = normalizeEvidence(text);
        String normalizedQuote = normalizeEvidence(quote);
        return normalizedQuote.length() >= 8 && normalizedText.contains(normalizedQuote);
    }

    private static String normalizeEvidence(String value) {
        return java.text.Normalizer.normalize(value == null ? "" : value, java.text.Normalizer.Form.NFKC)
                .replaceAll("\\s+", " ").trim().toLowerCase(java.util.Locale.ROOT);
    }

    private void replaceAnswers(Question question, QuizDtos.QuestionRequest request) {
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

    private void clearExistingAnswers(UUID questionId) {
        options.deleteByQuestionId(questionId);
        acceptedAnswers.deleteByQuestionId(questionId);
        options.flush();
        acceptedAnswers.flush();
    }

    public static void validate(QuizDtos.QuestionRequest request) {
        if (request == null || request.type() == null || request.prompt() == null || request.prompt().isBlank()) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "Câu hỏi phải có loại và nội dung hợp lệ");
        }
        if (request.cognitiveLevel() == null
                && (request.difficulty() == null || request.difficulty() == Difficulty.MIXED)) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "COGNITIVE_LEVEL_INVALID");
        }
        if (request.complexityProfile() != null && request.complexityProfile().verified()) {
            CognitivePolicy.validate(request.resolvedCognitiveLevel(), request.complexityProfile());
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
            String normalizedPrompt = normalizePrompt(request.prompt());
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

    static void validateUsableGeneratedBatch(List<QuizDtos.QuestionRequest> generated) {
        if (generated == null || generated.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT,
                    "AI không tạo được câu hỏi có thể sử dụng");
        }
        generated.forEach(QuestionService::validate);
    }

    private static List<QuizDtos.CitationRequest> safeCitations(
            QuizDtos.GroundedQuestion question) {
        return question.citations() == null ? List.of() : question.citations();
    }

    private static String normalizePrompt(String prompt) {
        return Normalizer.normalize(prompt == null ? "" : prompt, Normalizer.Form.NFKC)
                .toLowerCase(Locale.ROOT)
                .replaceAll("\\s+", " ")
                .trim();
    }

    private QuizDtos.QuestionResponse authorResponse(Question question) {
        var optionDtos = options.findByQuestionIdOrderByPosition(question.getId()).stream()
                .map(option -> new QuizDtos.OptionResponse(option.getId(), option.getOptionText(), option.isCorrect(),
                        option.getPosition())).toList();
        var answers = acceptedAnswers.findByQuestionIdOrderByPosition(question.getId()).stream()
                .map(AcceptedAnswer::getAnswerText).toList();
        List<QuizDtos.CitationResponse> citationDtos = citations == null ? List.of()
                : citations.findByQuestionIdOrderByRoleAscPositionAsc(question.getId()).stream().map(citation -> {
                    var chunk = sourceChunks.findById(citation.getSourceChunkId()).orElseThrow();
                    var document = sourceDocuments.findById(chunk.getSourceDocumentId()).orElseThrow();
                    return new QuizDtos.CitationResponse(chunk.getId(), chunk.getSourceDocumentId(), document.getName(),
                            chunk.getPageNumber(), chunk.getSlideNumber(), chunk.getChunkIndex(), chunk.getHeading(),
                            citation.getRole(), citation.getEvidenceQuote());
                }).toList();
        return new QuizDtos.QuestionResponse(question.getId(), question.getQuizId(), question.getType(),
                question.getPrompt(), question.getExplanation(), question.getPoints(), question.getPosition(),
                question.getDifficulty(), question.getCognitiveLevel(),
                profile(question), question.getComplexityScore(), question.getSourceChunkId(), optionDtos, answers, citationDtos,
                question.getAiValidationStatus(), question.getValidationWarnings(),
                question.getValidationReviewedAt(), question.getValidationReviewedBy(),
                question.getValidationReviewNote(),
                question.getVersion());
    }

    private Question newQuestion(UUID quizId, UUID sourceChunkId, QuizDtos.QuestionRequest request, int position) {
        Question question = new Question(quizId, sourceChunkId, request.type(), request.prompt(),
                request.explanation(), request.points(), position, request.difficulty());
        applyCognitive(question, request);
        return question;
    }

    private void applyCognitive(Question question, QuizDtos.QuestionRequest request) {
        CognitiveProfile profile = request.complexityProfile();
        if (profile == null) profile = new CognitiveProfile(0, 0, false, false, false, List.of(), null, false);
        String metadata = "{}";
        try {
            metadata = new tools.jackson.databind.ObjectMapper().writeValueAsString(
                    java.util.Map.of("conceptsUsed", profile.conceptsUsed(),
                            "novelScenarioSummary", profile.novelScenarioSummary() == null ? "" : profile.novelScenarioSummary()));
        } catch (Exception ignored) {
            // Empty metadata remains safe; scalar columns are authoritative.
        }
        question.applyCognitiveProfile(request.resolvedCognitiveLevel(), profile, metadata);
    }

    private CognitiveProfile profile(Question question) {
        if (!question.isComplexityVerified()) {
            return new CognitiveProfile(0, 0, false, false, false, List.of(), null, false);
        }
        return new CognitiveProfile(question.getConceptCount(), question.getReasoningStepCount(),
                Boolean.TRUE.equals(question.getRequiresNovelScenario()),
                Boolean.TRUE.equals(question.getAnswerDirectlyPresent()),
                Boolean.TRUE.equals(question.getRequiresComparison()), List.of(), null, true);
    }

    private Question require(UUID questionId) {
        return questions.findById(questionId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Không tìm thấy câu hỏi"));
    }

    private static void requireEditable(Quiz quiz) {
        if (quiz.getStatus() != QuizStatus.DRAFT
                && quiz.getStatus() != QuizStatus.READY
                && quiz.getStatus() != QuizStatus.PUBLISHED) {
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                    "Không thể sửa câu hỏi ở trạng thái hiện tại của bài kiểm tra");
        }
    }

}
