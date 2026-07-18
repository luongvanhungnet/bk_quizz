package com.genquiz.bk.storage;

import com.genquiz.bk.common.api.ApiEnvelope;
import com.genquiz.bk.user.dto.UserDto;
import org.springframework.core.io.InputStreamResource;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.UUID;
import java.util.concurrent.TimeUnit;

@RestController
public class AvatarController {
    private final AvatarService service;
    public AvatarController(AvatarService service) { this.service = service; }

    @PostMapping(value = "/api/users/me/avatar", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    ApiEnvelope<UserDto> upload(@RequestPart("file") MultipartFile file) {
        return ApiEnvelope.success("Cập nhật ảnh đại diện thành công.", service.upload(file));
    }

    @DeleteMapping("/api/users/me/avatar")
    ApiEnvelope<UserDto> delete() {
        return ApiEnvelope.success("Đã xóa ảnh đại diện.", service.delete());
    }

    @GetMapping("/api/avatars/{userId}")
    ResponseEntity<InputStreamResource> read(@PathVariable UUID userId) {
        AvatarService.AvatarContent content = service.read(userId);
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(content.mediaType()))
                .contentLength(content.size())
                .eTag('"' + content.etag() + '"')
                .cacheControl(CacheControl.maxAge(1, TimeUnit.DAYS).cachePublic())
                .header(HttpHeaders.CONTENT_DISPOSITION, "inline")
                .body(new InputStreamResource(content.input()));
    }
}
