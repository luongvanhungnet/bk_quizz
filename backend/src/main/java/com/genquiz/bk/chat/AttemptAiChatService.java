package com.genquiz.bk.chat;

import com.genquiz.bk.attempt.Attempt;
import com.genquiz.bk.attempt.AttemptAnswer;
import com.genquiz.bk.attempt.AttemptAnswerRepository;
import com.genquiz.bk.attempt.AttemptDtos;
import com.genquiz.bk.attempt.AttemptQuestionSnapshot;
import com.genquiz.bk.attempt.AttemptQuestionSnapshotRepository;
import com.genquiz.bk.attempt.AttemptRepository;
import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.rag.RagDtos;
import jakarta.transaction.Transactional;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Service
public class AttemptAiChatService {
    private final AttemptRepository attempts;
    private final AttemptQuestionSnapshotRepository snapshots;
    private final AttemptAnswerRepository answers;
    private final ChatThreadRepository threads;
    private final ChatMessageRepository messages;
    private final ChatCitationRepository citations;
    private final ObjectMapper mapper;
    private final Clock clock = Clock.systemUTC();

    public AttemptAiChatService(AttemptRepository attempts,
                                AttemptQuestionSnapshotRepository snapshots,
                                AttemptAnswerRepository answers,
                                ChatThreadRepository threads,
                                ChatMessageRepository messages,
                                ChatCitationRepository citations,
                                ObjectMapper mapper) {
        this.attempts = attempts;
        this.snapshots = snapshots;
        this.answers = answers;
        this.threads = threads;
        this.messages = messages;
        this.citations = citations;
        this.mapper = mapper;
    }

    public record Prepared(UUID threadId, UUID userMessageId, UUID assistantMessageId,
                           RagDtos.TutorRequest request, String replayContent,
                           List<AttemptAiChatDtos.Citation> replayCitations) {}

    @Transactional
    public Prepared prepare(UUID actorId, UUID attemptId, AttemptAiChatDtos.SendRequest input) {
        Attempt attempt = requireReview(actorId, attemptId);
        AttemptQuestionSnapshot snapshot = snapshots.findByIdAndAttemptId(input.snapshotId(), attemptId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "QUESTION_NOT_FOUND",
                        "Không tìm thấy câu hỏi trong lượt làm bài."));
        ChatThread thread = activeThread(actorId, attempt, true);
        var duplicate = messages.findByThreadIdAndClientMessageId(thread.getId(), input.clientMessageId());
        if (duplicate.isPresent()) {
            ChatMessage user = duplicate.get();
            ChatMessage assistant = messages.findByThreadIdAndReplyToMessageId(thread.getId(), user.getId())
                    .orElseThrow(() -> new ApiException(HttpStatus.CONFLICT, "CHAT_REQUEST_INCOMPLETE",
                            "Yêu cầu chat trước đó chưa hoàn tất."));
            if (assistant.getStatus() == ChatMessageStatus.COMPLETED) {
                return new Prepared(thread.getId(), user.getId(), assistant.getId(), null,
                        assistant.getContent(), citationsFor(assistant.getId()));
            }
            throw inProgress();
        }
        if (messages.existsByThreadIdAndRoleAndStatusIn(thread.getId(), ChatRole.ASSISTANT,
                List.of(ChatMessageStatus.PENDING, ChatMessageStatus.GENERATING))) {
            throw inProgress();
        }
        Instant now = clock.instant();
        ChatMessage user = messages.save(ChatMessage.user(
                thread.getId(), snapshot.getId(), input.clientMessageId(), input.message().trim(), now));
        ChatMessage assistant = ChatMessage.pendingAssistant(thread.getId(), snapshot.getId(), user.getId(), now);
        assistant.generating();
        messages.save(assistant);
        thread.touch(now);
        return new Prepared(thread.getId(), user.getId(), assistant.getId(),
                tutorRequest(attempt, snapshot, input.message().trim(), thread.getId(), user.getId()),
                null, List.of());
    }

    @Transactional
    public Prepared prepareRegenerate(UUID actorId, UUID attemptId, UUID assistantMessageId) {
        Attempt attempt = requireReview(actorId, attemptId);
        ChatThread thread = activeThread(actorId, attempt, false);
        ChatMessage oldAssistant = messages.findByIdAndThreadId(assistantMessageId, thread.getId())
                .filter(value -> value.getRole() == ChatRole.ASSISTANT)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "CHAT_MESSAGE_NOT_FOUND",
                        "Không tìm thấy phản hồi AI."));
        if (messages.existsByThreadIdAndRoleAndStatusIn(thread.getId(), ChatRole.ASSISTANT,
                List.of(ChatMessageStatus.PENDING, ChatMessageStatus.GENERATING))) throw inProgress();
        ChatMessage user = messages.findByIdAndThreadId(oldAssistant.getReplyToMessageId(), thread.getId())
                .orElseThrow(() -> new ApiException(HttpStatus.CONFLICT, "CHAT_HISTORY_INVALID",
                        "Không thể khôi phục yêu cầu cần thử lại."));
        AttemptQuestionSnapshot snapshot = snapshots.findByIdAndAttemptId(
                        oldAssistant.getQuestionSnapshotId(), attemptId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "QUESTION_NOT_FOUND",
                        "Không tìm thấy câu hỏi trong lượt làm bài."));
        ChatMessage replacement = ChatMessage.pendingAssistant(
                thread.getId(), snapshot.getId(), user.getId(), clock.instant());
        replacement.generating();
        messages.save(replacement);
        return new Prepared(thread.getId(), user.getId(), replacement.getId(),
                tutorRequest(attempt, snapshot, user.getContent(), thread.getId(), user.getId()),
                null, List.of());
    }

    @Transactional
    public void complete(UUID assistantId, String content, String model,
                         Integer inputTokens, Integer outputTokens,
                         List<RagDtos.TutorSource> sourceSnapshots) {
        ChatMessage assistant = messages.findById(assistantId).orElseThrow();
        assistant.complete(content, model, inputTokens, outputTokens, clock.instant());
        citations.deleteByMessageId(assistantId);
        int index = 0;
        for (RagDtos.TutorSource source : sourceSnapshots) {
            var snapshot = new AttemptAiChatDtos.Citation(source.sourceChunkId(),
                    source.sourceDocumentId(), source.filename(), source.pageNumber(),
                    source.slideNumber(), source.chunkIndex(), source.heading(),
                    source.evidenceQuote());
            citations.save(new ChatCitation(assistantId, source.sourceChunkId(), index++,
                    source.evidenceQuote(), null, write(snapshot)));
        }
    }

    @Transactional
    public void fail(UUID assistantId, String code, String message) {
        messages.findById(assistantId).ifPresent(value -> value.fail(code, message, clock.instant()));
    }

    @Transactional
    public void cancel(UUID assistantId, String partial) {
        messages.findById(assistantId).ifPresent(value -> value.cancel(partial, clock.instant()));
    }

    @Transactional
    public AttemptAiChatDtos.History history(UUID actorId, UUID attemptId, UUID afterId, int limit) {
        Attempt attempt = requireReview(actorId, attemptId);
        ChatThread thread = threads.findByAttemptIdAndUserIdAndDeletedAtIsNull(attempt.getId(), actorId)
                .orElse(null);
        if (thread == null) return new AttemptAiChatDtos.History(List.of(), afterId, false);
        List<ChatMessage> all = messages.findByThreadIdOrderByCreatedAt(thread.getId());
        int start = 0;
        if (afterId != null) {
            for (int i = 0; i < all.size(); i++) if (all.get(i).getId().equals(afterId)) start = i + 1;
        }
        int end = Math.min(all.size(), start + Math.max(1, Math.min(100, limit)));
        List<AttemptAiChatDtos.Message> page = all.subList(start, end).stream().map(this::dto).toList();
        return new AttemptAiChatDtos.History(page,
                page.isEmpty() ? afterId : page.get(page.size() - 1).id(), end < all.size());
    }

    @Transactional
    public void clear(UUID actorId, UUID attemptId) {
        Attempt attempt = requireReview(actorId, attemptId);
        ChatThread thread = threads.findByAttemptIdAndUserIdAndDeletedAtIsNull(attempt.getId(), actorId)
                .orElse(null);
        if (thread == null) return;
        if (messages.existsByThreadIdAndRoleAndStatusIn(thread.getId(), ChatRole.ASSISTANT,
                List.of(ChatMessageStatus.PENDING, ChatMessageStatus.GENERATING))) throw inProgress();
        thread.softDelete(clock.instant());
    }

    private ChatThread activeThread(UUID actorId, Attempt attempt, boolean create) {
        ChatThread thread = threads.findByAttemptIdAndUserIdAndDeletedAtIsNull(attempt.getId(), actorId).orElse(null);
        if (thread != null) {
            try {
                thread.requireActive(clock.instant());
                return thread;
            } catch (IllegalStateException expired) {
                thread.softDelete(clock.instant());
                threads.flush();
            }
        }
        if (!create) throw new ApiException(HttpStatus.NOT_FOUND, "CHAT_NOT_FOUND", "Chưa có hội thoại AI.");
        return threads.save(new ChatThread(actorId, null, null, attempt.getId(), "Trợ giảng kết quả Quiz", clock.instant()));
    }

    private Attempt requireReview(UUID actorId, UUID attemptId) {
        Attempt attempt = attempts.findByIdAndUserId(attemptId, actorId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "ATTEMPT_NOT_FOUND",
                        "Không tìm thấy lượt làm bài."));
        if (!attempt.isAllowReview() || !attempt.answersMayBeReleased(clock.instant())) {
            throw new ApiException(HttpStatus.UNPROCESSABLE_CONTENT, "ANSWER_REVIEW_NOT_AVAILABLE",
                    "Đáp án chưa được công bố nên trợ giảng AI chưa thể sử dụng câu hỏi này.");
        }
        return attempt;
    }

    private RagDtos.TutorRequest tutorRequest(Attempt attempt, AttemptQuestionSnapshot snapshot,
                                               String message, UUID threadId, UUID excludeMessageId) {
        List<SnapshotOption> optionValues = read(snapshot.getOptionsPayload(), new TypeReference<>() {});
        AnswerKey key = read(snapshot.getAnswerKey(), AnswerKey.class);
        Map<UUID, String> optionText = new LinkedHashMap<>();
        optionValues.forEach(value -> optionText.put(value.id(), value.text()));
        AttemptAnswer learner = answers.findByAttemptIdAndSnapshotId(attempt.getId(), snapshot.getId()).orElse(null);
        String learnerAnswer = learner == null ? null : answerText(
                read(learner.getSelectedOptionIds(), new TypeReference<>() {}), learner.getTextAnswer(), optionText);
        String correctAnswer = answerText(key.correctOptionIds(),
                key.acceptedAnswers() == null ? null : String.join("; ", key.acceptedAnswers()), optionText);
        List<AttemptDtos.Citation> sourceValues = read(snapshot.getCitationsPayload(), new TypeReference<>() {});
        Map<String, RagDtos.TutorSource> uniqueSources = new LinkedHashMap<>();
        int sourceNumber = 1;
        for (AttemptDtos.Citation source : sourceValues) {
            String keyValue = source.sourceChunkId() + "|" + source.evidenceQuote();
            if (!uniqueSources.containsKey(keyValue)) {
                String marker = "S" + sourceNumber++;
                uniqueSources.put(keyValue, new RagDtos.TutorSource(marker, source.sourceChunkId(),
                        source.sourceDocumentId(), source.filename(), source.pageNumber(), source.slideNumber(),
                        source.chunkIndex(), source.heading(), source.evidenceQuote()));
            }
        }
        List<ChatMessage> history = messages.findByThreadIdOrderByCreatedAt(threadId).stream()
                .filter(value -> !value.getId().equals(excludeMessageId))
                .filter(value -> !excludeMessageId.equals(value.getReplyToMessageId()))
                .filter(value -> value.getStatus() == ChatMessageStatus.COMPLETED)
                .toList();
        if (history.size() > 12) history = history.subList(history.size() - 12, history.size());
        List<RagDtos.TutorHistory> conversation = history.stream()
                .map(value -> new RagDtos.TutorHistory(
                        value.getRole() == ChatRole.USER ? "user" : "assistant", value.getContent()))
                .toList();
        return new RagDtos.TutorRequest(snapshot.getPosition() + 1, snapshot.getQuestionType().name(),
                snapshot.getPrompt(), optionValues.stream().map(SnapshotOption::text).toList(),
                learnerAnswer, correctAnswer, snapshot.getExplanation(),
                new ArrayList<>(uniqueSources.values()), conversation, message);
    }

    private String answerText(List<UUID> ids, String text, Map<UUID, String> options) {
        List<String> values = ids == null ? new ArrayList<>() : ids.stream()
                .map(options::get).filter(Objects::nonNull).toList();
        if (!values.isEmpty()) return String.join("; ", values);
        return text == null || text.isBlank() ? "Không có câu trả lời" : text;
    }

    private AttemptAiChatDtos.Message dto(ChatMessage value) {
        return new AttemptAiChatDtos.Message(value.getId(), value.getQuestionSnapshotId(),
                value.getRole().name(), value.getStatus().name(), value.getContent(), value.getModel(),
                value.getErrorCode(), value.getErrorMessage(), value.getReplyToMessageId(),
                value.getCreatedAt(), value.getCompletedAt(), citationsFor(value.getId()));
    }

    private List<AttemptAiChatDtos.Citation> citationsFor(UUID messageId) {
        return citations.findByMessageIdOrderByCitationIndex(messageId).stream().map(value ->
                read(value.getCitationSnapshot(), AttemptAiChatDtos.Citation.class)).toList();
    }

    private ApiException inProgress() {
        return new ApiException(HttpStatus.CONFLICT, "CHAT_RESPONSE_IN_PROGRESS",
                "Trợ giảng AI đang trả lời một yêu cầu khác.");
    }

    private <T> T read(String value, Class<T> type) {
        try { return mapper.readValue(value, type); }
        catch (Exception error) { throw new IllegalStateException("Dữ liệu snapshot không hợp lệ", error); }
    }
    private <T> T read(String value, TypeReference<T> type) {
        try { return mapper.readValue(value, type); }
        catch (Exception error) { throw new IllegalStateException("Dữ liệu snapshot không hợp lệ", error); }
    }
    private String write(Object value) {
        try { return mapper.writeValueAsString(value); }
        catch (Exception error) { throw new IllegalStateException("Không thể lưu nguồn chat", error); }
    }

    private record SnapshotOption(UUID id, String text, int position) {}
    private record AnswerKey(List<UUID> correctOptionIds, List<String> acceptedAnswers) {}
}
