package com.genquiz.bk.topic;

import jakarta.validation.Valid;
import java.net.URI;
import java.security.Principal;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import com.genquiz.bk.security.CurrentUser;

@RestController
@RequestMapping("/api/topics")
public class TopicController {
    private final TopicService service;
    private final ActorIdentityService actors;
    private final CurrentUser currentUser;

    public TopicController(TopicService service, ActorIdentityService actors, CurrentUser currentUser) {
        this.service = service;
        this.actors = actors;
        this.currentUser = currentUser;
    }

    @PostMapping
    public ResponseEntity<TopicDtos.Response> create(@Valid @RequestBody TopicDtos.SaveRequest request,
                                                      Principal principal) {
        Topic topic = service.create(actors.requireUserId(principal), request);
        return ResponseEntity.created(URI.create("/api/topics/" + topic.getId())).body(TopicDtos.Response.from(topic));
    }

    @GetMapping
    public Page<TopicDtos.Response> list(Principal principal, Pageable pageable) {
        return service.listOwned(actors.requireUserId(principal), pageable).map(TopicDtos.Response::from);
    }

    @GetMapping("/{topicId}")
    public TopicDtos.Response get(@PathVariable UUID topicId, Principal principal) {
        return TopicDtos.Response.from(service.getAccessible(actors.requireUserId(principal), topicId));
    }

    @PutMapping("/{topicId}")
    public TopicDtos.Response update(@PathVariable UUID topicId,
                                     @Valid @RequestBody TopicDtos.SaveRequest request,
                                     Principal principal) {
        return TopicDtos.Response.from(service.update(actors.requireUserId(principal), topicId, request));
    }

    @PostMapping("/{topicId}/publish")
    public TopicDtos.Response publish(@PathVariable UUID topicId, Principal principal) {
        currentUser.requireVerified();
        return TopicDtos.Response.from(service.publish(actors.requireUserId(principal), topicId));
    }

    @DeleteMapping("/{topicId}")
    public ResponseEntity<Void> delete(@PathVariable UUID topicId, Principal principal) {
        // Dependency-aware soft deletion is enforced again by database/service integrations.
        service.delete(actors.requireUserId(principal), topicId, false);
        return ResponseEntity.noContent().build();
    }
}
