package com.genquiz.bk.storage;

import com.genquiz.bk.config.AppProperties;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AvatarObjectStorageTest {
    @TempDir Path temp;

    @Test
    void storesAvatarInConfiguredS3Bucket() throws Exception {
        S3Client s3 = mock(S3Client.class);
        when(s3.putObject(any(PutObjectRequest.class), any(software.amazon.awssdk.core.sync.RequestBody.class)))
                .thenReturn(software.amazon.awssdk.services.s3.model.PutObjectResponse.builder().build());
        AvatarObjectStorage storage = new AvatarObjectStorage(
                s3, properties(), "s3", temp.resolve("local").toString(), temp.resolve("tmp").toString());
        Path avatar = temp.resolve("avatar.jpg");
        Files.write(avatar, new byte[]{1, 2, 3});
        UUID ownerId = UUID.randomUUID();

        AvatarObjectStorage.Stored stored = storage.store(ownerId, avatar, ".jpg", "image/jpeg");

        assertThat(stored.provider()).isEqualTo(StoredFile.Provider.S3);
        assertThat(stored.path()).startsWith("avatars/" + ownerId + "/").endsWith(".jpg");
        verify(s3).putObject(
                org.mockito.ArgumentMatchers.<PutObjectRequest>argThat(request ->
                        request.bucket().equals("bkquiz-test")
                                && request.key().equals(stored.path())
                                && request.contentType().equals("image/jpeg")),
                any(software.amazon.awssdk.core.sync.RequestBody.class));
    }

    private AppProperties properties() {
        return new AppProperties(
                List.of("https://quiz.example.com"),
                new AppProperties.Security("test-secret-at-least-32-characters-long", Duration.ofMinutes(15),
                        Duration.ofDays(7), "refresh", "XSRF-TOKEN", true, 12),
                new AppProperties.Storage("https://account.r2.cloudflarestorage.com", "auto",
                        "access", "secret", "bkquiz-test", true),
                new AppProperties.Ai(false, "model", "embedding", 768, Duration.ofSeconds(60), 3, 100, 10, 100),
                new AppProperties.Jobs(false, Duration.ofSeconds(2), Duration.ofMinutes(2), 5));
    }
}
