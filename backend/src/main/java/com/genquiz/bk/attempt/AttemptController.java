package com.genquiz.bk.attempt;

import com.genquiz.bk.topic.ActorIdentityService;
import jakarta.validation.Valid;
import java.security.Principal;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class AttemptController {
    private final AttemptService service;
    private final ActorIdentityService actors;

    public AttemptController(AttemptService service, ActorIdentityService actors) {
        this.service = service;
        this.actors = actors;
    }

    @PostMapping("/quizzes/{quizId}/attempts")
    public ResponseEntity<AttemptDtos.AttemptResponse> start(@PathVariable UUID quizId,
                                                             @RequestBody(required = false)
                                                             AttemptDtos.StartRequest request,
                                                             Principal principal) {
        UUID assignmentId = request == null ? null : request.assignmentId();
        var response = service.start(actors.requireUserId(principal), quizId, assignmentId);
        return ResponseEntity.created(java.net.URI.create("/api/attempts/" + response.id())).body(response);
    }

    @GetMapping("/attempts/{attemptId}")
    public AttemptDtos.AttemptResponse get(@PathVariable UUID attemptId, Principal principal) {
        return service.get(actors.requireUserId(principal), attemptId);
    }

    @PutMapping("/attempts/{attemptId}/answers")
    public AttemptDtos.AttemptResponse autosave(@PathVariable UUID attemptId,
                                                @Valid @RequestBody AttemptDtos.AutosaveRequest request,
                                                Principal principal) {
        return service.autosave(actors.requireUserId(principal), attemptId, request);
    }

    @PostMapping("/attempts/{attemptId}/submit")
    public AttemptDtos.ResultResponse submit(@PathVariable UUID attemptId,
                                             @RequestHeader("Idempotency-Key") String idempotencyKey,
                                             Principal principal) {
        return service.submit(actors.requireUserId(principal), attemptId, idempotencyKey);
    }

    @GetMapping("/attempts/{attemptId}/result")
    public AttemptDtos.ResultResponse result(@PathVariable UUID attemptId, Principal principal) {
        return service.result(actors.requireUserId(principal), attemptId);
    }

    @GetMapping("/attempts")
    public Page<AttemptDtos.HistoryItem> history(Principal principal, Pageable pageable) {
        return service.history(actors.requireUserId(principal), pageable);
    }
}
