package com.genquiz.bk.source;

import com.genquiz.bk.job.Job;
import com.genquiz.bk.topic.ActorIdentityService;
import jakarta.validation.Valid;
import java.net.URI;
import java.security.Principal;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api")
public class SourceController {
    private final SourceService service;
    private final ActorIdentityService actors;
    private final SourcePresentationService presentation;

    public SourceController(SourceService service, ActorIdentityService actors,
                            SourcePresentationService presentation) {
        this.service = service;
        this.actors = actors;
        this.presentation = presentation;
    }

    @PostMapping("/topics/{topicId}/sources/text")
    public ResponseEntity<SourceDtos.Response> paste(@PathVariable UUID topicId,
                                                     @Valid @RequestBody SourceDtos.PasteRequest request,
                                                     Principal principal) {
        SourceDocument source = service.paste(actors.requireUserId(principal), topicId, request);
        return ResponseEntity.created(URI.create("/api/sources/" + source.getId()))
                .body(presentation.response(source));
    }

    @PostMapping(value = "/topics/{topicId}/sources/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<SourceDtos.UploadResponse> upload(
            @PathVariable UUID topicId,
            @RequestPart("file") MultipartFile file,
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
            Principal principal) {
        var result = service.upload(actors.requireUserId(principal), topicId, file, idempotencyKey);
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .header(HttpHeaders.LOCATION, "/api/jobs/" + result.job().getId())
                .body(new SourceDtos.UploadResponse(presentation.response(result.source()), result.job().getId()));
    }

    @GetMapping("/topics/{topicId}/sources")
    public List<SourceDtos.Response> list(@PathVariable UUID topicId, Principal principal) {
        return service.list(actors.requireUserId(principal), topicId).stream()
                .map(presentation::response).toList();
    }

    @GetMapping("/sources/{sourceId}")
    public SourceDtos.Response get(@PathVariable UUID sourceId, Principal principal) {
        return presentation.response(service.getOwned(actors.requireUserId(principal), sourceId));
    }

    @DeleteMapping("/sources/{sourceId}")
    public ResponseEntity<Void> delete(@PathVariable UUID sourceId, Principal principal) {
        service.delete(actors.requireUserId(principal), sourceId);
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/sources/{sourceId}/reindex")
    public ResponseEntity<SourceDtos.UploadResponse> reindex(@PathVariable UUID sourceId, Principal principal) {
        UUID actorId = actors.requireUserId(principal);
        Job job = service.reindex(actorId, sourceId);
        SourceDocument source = service.getOwned(actorId, sourceId);
        return ResponseEntity.accepted().header(HttpHeaders.LOCATION, "/api/jobs/" + job.getId())
                .body(new SourceDtos.UploadResponse(presentation.response(source), job.getId()));
    }
}
