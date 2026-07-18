package com.genquiz.bk.explore;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/explore/topics")
public class ExploreController {
    private final ExploreService service;
    public ExploreController(ExploreService service) { this.service = service; }

    @GetMapping
    public Page<ExploreDtos.TopicSummary> list(@RequestParam(defaultValue = "") String q,
                                               @RequestParam(defaultValue = "recent") String sort,
                                               @RequestParam(defaultValue = "1") @Min(1) int page,
                                               @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit) {
        return service.list(q, sort, page, limit);
    }
    @GetMapping("/{topicId}")
    public ExploreDtos.TopicDetail detail(@PathVariable UUID topicId) { return service.detail(topicId); }
}
