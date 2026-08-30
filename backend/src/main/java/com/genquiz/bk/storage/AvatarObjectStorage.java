package com.genquiz.bk.storage;

import com.genquiz.bk.config.AppProperties;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.UUID;

/** Stores avatars in the configured durable provider while retaining support for legacy local files. */
@Component
public class AvatarObjectStorage {
    private static final Logger log = LoggerFactory.getLogger(AvatarObjectStorage.class);
    private final S3Client s3;
    private final AppProperties properties;
    private final LocalFileStorage local;
    private final boolean localProvider;

    public AvatarObjectStorage(S3Client s3, AppProperties properties,
                               @Value("${bkquiz.storage.provider:local}") String provider,
                               @Value("${bkquiz.storage.local-root:./data/uploads}") String root,
                               @Value("${bkquiz.storage.local-temp:./data/tmp}") String temp) {
        this.s3 = s3;
        this.properties = properties;
        this.local = new LocalFileStorage(Path.of(root), Path.of(temp));
        this.localProvider = "local".equalsIgnoreCase(provider);
    }

    public Stored store(UUID ownerId, Path source, String extension, String mediaType) throws IOException {
        if (localProvider) {
            try (InputStream input = Files.newInputStream(source)) {
                Stored stored = new Stored(local.store("avatar", extension, input), StoredFile.Provider.LOCAL);
                log.info("Avatar object stored provider=local sizeBytes={}", Files.size(source));
                return stored;
            }
        }

        String safeExtension = extension == null ? "" : extension.toLowerCase(Locale.ROOT);
        String key = "avatars/" + ownerId + "/" + UUID.randomUUID() + safeExtension;
        s3.putObject(PutObjectRequest.builder()
                        .bucket(properties.storage().bucket())
                        .key(key)
                        .contentType(mediaType)
                        .contentLength(Files.size(source))
                        .build(),
                RequestBody.fromFile(source));
        log.info("Avatar object stored provider=s3 bucket={} sizeBytes={}",
                properties.storage().bucket(), Files.size(source));
        return new Stored(key, StoredFile.Provider.S3);
    }

    public InputStream read(StoredFile.Provider provider, String path) throws IOException {
        if (provider == StoredFile.Provider.LOCAL) {
            return local.read(path);
        }
        try {
            ResponseInputStream<GetObjectResponse> response = s3.getObject(GetObjectRequest.builder()
                    .bucket(properties.storage().bucket())
                    .key(path)
                    .build());
            return response;
        } catch (RuntimeException exception) {
            throw new IOException("Không thể đọc ảnh đại diện từ object storage.", exception);
        }
    }

    public void delete(StoredFile.Provider provider, String path) {
        if (path == null) return;
        if (provider == StoredFile.Provider.LOCAL) {
            try { local.delete(path); } catch (IOException ignored) { }
            return;
        }
        s3.deleteObject(DeleteObjectRequest.builder()
                .bucket(properties.storage().bucket())
                .key(path)
                .build());
    }

    public record Stored(String path, StoredFile.Provider provider) { }
}
