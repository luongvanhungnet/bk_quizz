package com.genquiz.bk.chat;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "chat_messages")
public class ChatMessage {
    @Id private UUID id;
    @Column(name = "thread_id", nullable = false, updatable = false) private UUID threadId;
    @Column(name = "job_id") private UUID jobId;
    @Enumerated(EnumType.STRING) @Column(nullable = false, length = 20) private ChatRole role;
    @Enumerated(EnumType.STRING) @Column(nullable = false, length = 20) private ChatMessageStatus status;
    @Column(nullable = false, columnDefinition = "text") private String content;
    @Column(length = 100) private String model;
    @Column(name = "prompt_tokens") private Integer promptTokens;
    @Column(name = "completion_tokens") private Integer completionTokens;
    @Column(name = "total_tokens") private Integer totalTokens;
    @Column(name = "error_code", length = 80) private String errorCode;
    @Column(name = "error_message", length = 1000) private String errorMessage;
    @Column(name = "created_at", nullable = false, updatable = false) private Instant createdAt;
    @Column(name = "completed_at") private Instant completedAt;

    protected ChatMessage() {}
    public static ChatMessage user(UUID threadId, String content, Instant now) {
        ChatMessage message = base(threadId, ChatRole.USER, ChatMessageStatus.COMPLETED, content, now);
        message.completedAt = now; return message;
    }
    public static ChatMessage pendingAssistant(UUID threadId, Instant now) {
        return base(threadId, ChatRole.ASSISTANT, ChatMessageStatus.PENDING, "", now);
    }
    private static ChatMessage base(UUID threadId, ChatRole role, ChatMessageStatus status, String content, Instant now) {
        ChatMessage message = new ChatMessage(); message.id = UUID.randomUUID(); message.threadId = threadId;
        message.role = role; message.status = status; message.content = content; message.createdAt = now; return message;
    }
    public void attachJob(UUID jobId) { this.jobId = jobId; }
    public void generating() {
        if (status != ChatMessageStatus.PENDING) throw new IllegalStateException("Tin nhắn không thể bắt đầu sinh phản hồi");
        status = ChatMessageStatus.GENERATING;
    }
    public void complete(String content, String model, Integer promptTokens, Integer completionTokens, Instant now) {
        if (content == null || content.isBlank()) throw new IllegalArgumentException("Phản hồi AI trống");
        this.content = content.trim(); this.model = model; this.promptTokens = promptTokens;
        this.completionTokens = completionTokens;
        this.totalTokens = promptTokens == null || completionTokens == null ? null : promptTokens + completionTokens;
        this.status = ChatMessageStatus.COMPLETED; this.completedAt = now; this.errorCode = null; this.errorMessage = null;
    }
    public void fail(String code, String message, Instant now) {
        status = ChatMessageStatus.FAILED; errorCode = code;
        errorMessage = message == null ? null : message.substring(0, Math.min(1000, message.length()));
        completedAt = null;
    }
    public UUID getId() { return id; } public UUID getThreadId() { return threadId; }
    public UUID getJobId() { return jobId; } public ChatRole getRole() { return role; }
    public ChatMessageStatus getStatus() { return status; } public String getContent() { return content; }
    public String getModel() { return model; } public Integer getPromptTokens() { return promptTokens; }
    public Integer getCompletionTokens() { return completionTokens; } public Integer getTotalTokens() { return totalTokens; }
    public String getErrorCode() { return errorCode; } public String getErrorMessage() { return errorMessage; }
    public Instant getCreatedAt() { return createdAt; } public Instant getCompletedAt() { return completedAt; }
}
