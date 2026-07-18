package com.genquiz.bk.job;

import com.genquiz.bk.topic.ActorIdentityService;
import java.security.Principal;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/jobs")
public class JobController {
    private final JobService service;
    private final ActorIdentityService actors;

    public JobController(JobService service, ActorIdentityService actors) {
        this.service = service;
        this.actors = actors;
    }

    @GetMapping("/{jobId}")
    public JobDtos.Response get(@PathVariable UUID jobId, Principal principal) {
        return JobDtos.Response.from(service.getOwned(actors.requireUserId(principal), jobId));
    }
}
