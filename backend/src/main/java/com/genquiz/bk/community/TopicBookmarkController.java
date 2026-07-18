package com.genquiz.bk.community;

import com.genquiz.bk.explore.ExploreDtos;
import com.genquiz.bk.topic.ActorIdentityService;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.security.Principal;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api")
public class TopicBookmarkController {
    private final TopicBookmarkService service;
    private final ActorIdentityService actors;
    public TopicBookmarkController(TopicBookmarkService service, ActorIdentityService actors) {
        this.service = service; this.actors = actors;
    }
    @PutMapping("/topics/{topicId}/bookmark")
    public ExploreDtos.SavedTopic bookmark(@PathVariable UUID topicId, Principal principal) {
        return service.bookmark(actors.requireUserId(principal), topicId);
    }
    @DeleteMapping("/topics/{topicId}/bookmark")
    public ResponseEntity<Void> unbookmark(@PathVariable UUID topicId, Principal principal) {
        service.unbookmark(actors.requireUserId(principal), topicId);
        return ResponseEntity.noContent().build();
    }
    @GetMapping("/topic-bookmarks")
    public Page<ExploreDtos.SavedTopic> list(@RequestParam(defaultValue = "1") @Min(1) int page,
                                             @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit,
                                             Principal principal) {
        return service.list(actors.requireUserId(principal), page, limit);
    }
}
