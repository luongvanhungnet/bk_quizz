package com.genquiz.bk.storage;

import org.springframework.core.io.InputStreamResource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/local-files")
public class LocalFileAccessController {
    private final ClassroomObjectStorage storage;
    public LocalFileAccessController(ClassroomObjectStorage storage){this.storage=storage;}
    @GetMapping("/{token}") ResponseEntity<InputStreamResource> read(@PathVariable String token){
        ClassroomObjectStorage.SignedContent value=storage.openSigned(token);
        return ResponseEntity.ok().contentType(MediaType.parseMediaType(value.mediaType())).contentLength(value.size()).body(new InputStreamResource(value.input()));
    }
}
