package com.genquiz.bk.storage;

import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.config.AppProperties;
import com.genquiz.bk.source.SourceObjectStorage;
import org.apache.tika.Tika;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.Map;
import java.util.Base64;
import java.util.Set;
import java.util.UUID;

@Component
@ConditionalOnProperty(name="bkquiz.storage.provider",havingValue="s3")
public class S3SourceObjectStorage implements SourceObjectStorage {
    private static final Set<String> ALLOWED = Set.of("application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation", "text/plain");
    private final S3Client s3;
    private final AppProperties properties;
    private final ClamAvScanner clamAv;
    private final Tika tika = new Tika();

    public S3SourceObjectStorage(S3Client s3, AppProperties properties, ClamAvScanner clamAv) {
        this.s3 = s3; this.properties = properties; this.clamAv = clamAv;
    }

    @Override
    public StoredObject scanAndStore(String requestedName, String declaredContentType, long sizeBytes, InputStream data)
            throws IOException {
        Path temp = Files.createTempFile("bkquiz-upload-", ".bin");
        try {
            Files.copy(data, temp, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
            String detected;
            try (InputStream detectionStream = Files.newInputStream(temp)) {
                detected = tika.detect(detectionStream, requestedName == null ? "document" : requestedName);
            }
            if (!ALLOWED.contains(detected)) {
                throw new ApiException(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "UNSUPPORTED_FILE_TYPE",
                        "Định dạng thực tế của tài liệu không được hỗ trợ.");
            }
            clamAv.requireClean(temp);
            String key = "sources/" + LocalDate.now() + "/" + UUID.randomUUID() + extension(requestedName);
            s3.putObject(PutObjectRequest.builder().bucket(properties.storage().bucket()).key(key)
                            .contentType(detected).contentLength(Files.size(temp))
                            .metadata(Map.of("original-name-b64", safeMetadata(requestedName))).build(),
                    RequestBody.fromFile(temp));
            return new StoredObject(key, detected, "S3", sha256(temp));
        } finally {
            Files.deleteIfExists(temp);
        }
    }

    @Override
    public InputStream read(String objectKey) throws IOException {
        try {
            ResponseInputStream<GetObjectResponse> response = s3.getObject(GetObjectRequest.builder()
                    .bucket(properties.storage().bucket()).key(objectKey).build());
            return response;
        } catch (RuntimeException exception) {
            throw new IOException("Không thể đọc tài liệu từ object storage.", exception);
        }
    }

    @Override
    public void delete(String objectKey) {
        if (objectKey == null) return;
        s3.deleteObject(DeleteObjectRequest.builder().bucket(properties.storage().bucket()).key(objectKey).build());
    }

    private String extension(String name) {
        if (name == null) return "";
        int dot = name.lastIndexOf('.');
        return dot >= 0 && name.length() - dot <= 10 ? name.substring(dot).toLowerCase() : "";
    }
    private String safeMetadata(String value) {
        if (value == null) return "document";
        String sanitized = value.replaceAll("[\\r\\n]", " ");
        if (sanitized.length() > 200) sanitized = sanitized.substring(0, 200);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(sanitized.getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }
    private String sha256(Path path) throws IOException {
        try { var digest=java.security.MessageDigest.getInstance("SHA-256"); try(InputStream in=Files.newInputStream(path)){in.transferTo(new java.security.DigestOutputStream(OutputStream.nullOutputStream(),digest));} return java.util.HexFormat.of().formatHex(digest.digest()); }
        catch(java.security.NoSuchAlgorithmException e){throw new IllegalStateException(e);}
    }
}
