package com.genquiz.bk.chat;

import com.genquiz.bk.topic.ActorIdentityService;
import com.genquiz.bk.rag.RagClient;
import com.genquiz.bk.rag.RagDtos;
import com.genquiz.bk.rag.RagServiceException;
import jakarta.validation.Valid;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.security.Principal;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

@RestController
@RequestMapping("/api/attempts/{attemptId}/ai-chat")
public class AttemptAiChatController {
    private final AttemptAiChatService service;
    private final ActorIdentityService actors;
    private final RagClient rag;
    private final ObjectMapper mapper;

    public AttemptAiChatController(AttemptAiChatService service, ActorIdentityService actors,
                                   RagClient rag, ObjectMapper mapper) {
        this.service = service;
        this.actors = actors;
        this.rag = rag;
        this.mapper = mapper;
    }

    @GetMapping("/messages")
    public AttemptAiChatDtos.History history(@PathVariable UUID attemptId,
                                             @RequestParam(required = false) UUID afterId,
                                             @RequestParam(defaultValue = "100") int limit,
                                             Principal principal) {
        return service.history(actors.requireUserId(principal), attemptId, afterId, limit);
    }

    @PostMapping(value = "/messages/stream", produces = "application/x-ndjson")
    public ResponseEntity<StreamingResponseBody> send(@PathVariable UUID attemptId,
                                                       @Valid @RequestBody AttemptAiChatDtos.SendRequest request,
                                                       Principal principal) {
        UUID actorId = actors.requireUserId(principal);
        AttemptAiChatService.Prepared prepared = service.prepare(actorId, attemptId, request);
        return stream(actorId, prepared);
    }

    @PostMapping(value = "/messages/{messageId}/regenerate/stream", produces = "application/x-ndjson")
    public ResponseEntity<StreamingResponseBody> regenerate(@PathVariable UUID attemptId,
                                                             @PathVariable UUID messageId,
                                                             Principal principal) {
        UUID actorId = actors.requireUserId(principal);
        return stream(actorId, service.prepareRegenerate(actorId, attemptId, messageId));
    }

    @DeleteMapping
    public ResponseEntity<Void> clear(@PathVariable UUID attemptId, Principal principal) {
        service.clear(actors.requireUserId(principal), attemptId);
        return ResponseEntity.noContent().build();
    }

    private ResponseEntity<StreamingResponseBody> stream(UUID actorId, AttemptAiChatService.Prepared prepared) {
        StreamingResponseBody body = output -> {
            StringBuilder answer = new StringBuilder();
            List<RagDtos.TutorSource> sources = new ArrayList<>();
            AtomicBoolean terminalSent = new AtomicBoolean();
            try {
                write(output, event("MESSAGE_STARTED", prepared.assistantMessageId(), null));
                if (prepared.replayContent() != null) {
                    write(output, event("DELTA", prepared.assistantMessageId(), prepared.replayContent()));
                    ObjectNode completed = event("COMPLETED", prepared.assistantMessageId(), null);
                    completed.set("sources", mapper.valueToTree(prepared.replayCitations()));
                    write(output, completed);
                    return;
                }
                rag.streamAttemptTutor(actorId, prepared.request(), event -> {
                    try {
                        String type = event.path("type").stringValue("");
                        if ("STARTED".equals(type)) return;
                        ObjectNode forwarded = (ObjectNode) event.deepCopy();
                        forwarded.put("assistantMessageId", prepared.assistantMessageId().toString());
                        if ("DELTA".equals(type)) answer.append(event.path("delta").stringValue(""));
                        if ("SOURCES".equals(type) && event.path("sources").isArray()) {
                            sources.clear();
                            event.path("sources").forEach(source ->
                                    sources.add(mapper.treeToValue(source, RagDtos.TutorSource.class)));
                        }
                        if ("FAILED".equals(type) || "CANCELLED".equals(type)) terminalSent.set(true);
                        if ("COMPLETED".equals(type)) {
                            JsonNode usage = event.path("usage");
                            service.complete(prepared.assistantMessageId(), answer.toString(),
                                    event.path("model").stringValue(null),
                                    usage.path("inputTokens").isNumber() ? usage.path("inputTokens").intValue() : null,
                                    usage.path("outputTokens").isNumber() ? usage.path("outputTokens").intValue() : null,
                                    sources);
                            terminalSent.set(true);
                        }
                        write(output, forwarded);
                    } catch (IOException exception) {
                        throw new UncheckedIOException(exception);
                    }
                });
            } catch (UncheckedIOException | IOException disconnected) {
                service.cancel(prepared.assistantMessageId(), answer.toString());
            } catch (RagServiceException failure) {
                service.fail(prepared.assistantMessageId(), failure.code(), failure.getMessage());
                if (!terminalSent.get()) {
                    ObjectNode failed = event("FAILED", prepared.assistantMessageId(), failure.getMessage());
                    failed.put("errorCode", failure.code());
                    failed.put("retryable", failure.retryable());
                    write(output, failed);
                }
            } catch (RuntimeException failure) {
                service.fail(prepared.assistantMessageId(), "AI_CHAT_FAILED",
                        "Không thể hoàn tất phản hồi AI.");
                if (!terminalSent.get()) {
                    ObjectNode failed = event("FAILED", prepared.assistantMessageId(),
                            "Không thể hoàn tất phản hồi AI.");
                    failed.put("errorCode", "AI_CHAT_FAILED");
                    write(output, failed);
                }
            }
        };
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType("application/x-ndjson"))
                .header("Cache-Control", "no-cache, no-transform")
                .header("X-Accel-Buffering", "no")
                .body(body);
    }

    private ObjectNode event(String type, UUID assistantId, String content) {
        ObjectNode event = mapper.createObjectNode();
        event.put("type", type);
        event.put("assistantMessageId", assistantId.toString());
        if ("DELTA".equals(type)) event.put("delta", content == null ? "" : content);
        else if (content != null) event.put("message", content);
        return event;
    }

    private void write(java.io.OutputStream output, JsonNode event) throws IOException {
        output.write((mapper.writeValueAsString(event) + "\n").getBytes(StandardCharsets.UTF_8));
        output.flush();
    }
}
