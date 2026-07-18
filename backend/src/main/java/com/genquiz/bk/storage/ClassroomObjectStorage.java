package com.genquiz.bk.storage;

import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.config.AppProperties;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.time.Duration;
import java.util.Set;
import java.util.UUID;
import java.util.Base64;
import java.nio.charset.StandardCharsets;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Value;
import org.apache.tika.Tika;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest;

@Component
public class ClassroomObjectStorage {
    private static final Set<String> IMAGES = Set.of("image/jpeg", "image/png", "image/webp", "image/gif");
    private static final Set<String> FILES = Set.of(
            "application/pdf", "application/zip", "text/plain",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");

    private final S3Client s3;
    private final AppProperties properties;
    private final ClamAvScanner clam;
    private final S3Presigner presigner;
    private final Tika tika = new Tika();
    private final boolean localProvider;
    private final LocalFileStorage local;
    private final byte[] signingKey;

    public ClassroomObjectStorage(S3Client s3, AppProperties properties, ClamAvScanner clam, S3Presigner presigner,
                                  @Value("${bkquiz.storage.provider:local}") String provider,
                                  @Value("${bkquiz.storage.local-root:./data/uploads}") String root,
                                  @Value("${bkquiz.storage.local-temp:./data/tmp}") String temp,
                                  @Value("${bkquiz.security.access-secret}") String secret) {
        this.s3 = s3;
        this.properties = properties;
        this.clam = clam;
        this.presigner = presigner;
        this.localProvider = "local".equalsIgnoreCase(provider);
        this.local = new LocalFileStorage(Path.of(root), Path.of(temp));
        this.signingKey = secret.getBytes(StandardCharsets.UTF_8);
    }

    public Stored store(MultipartFile file) throws IOException {
        if (file.isEmpty()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "EMPTY_FILE", "Tệp không được để trống.");
        }
        Path temp = Files.createTempFile("bkquiz-classroom-", ".bin");
        try {
            file.transferTo(temp);
            String detected;
            try (InputStream input = Files.newInputStream(temp)) {
                detected = tika.detect(input, file.getOriginalFilename());
            }
            boolean image = IMAGES.contains(detected);
            if (!image && !FILES.contains(detected)) {
                throw new ApiException(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "UNSUPPORTED_FILE_TYPE", "Định dạng tệp không được hỗ trợ.");
            }
            long limit = image ? 10L * 1024 * 1024 : 25L * 1024 * 1024;
            if (Files.size(temp) > limit) {
                throw new ApiException(HttpStatus.CONTENT_TOO_LARGE, "FILE_TOO_LARGE", "Tệp vượt quá giới hạn cho phép.");
            }
            clam.requireClean(temp);
            String key;
            if (localProvider) {
                String extension = extension(file.getOriginalFilename());
                try (InputStream input = Files.newInputStream(temp)) { key = "local:" + local.store("classroom", extension, input); }
            } else {
                key = "classrooms/" + LocalDate.now() + "/" + UUID.randomUUID();
                s3.putObject(
                    PutObjectRequest.builder()
                            .bucket(properties.storage().bucket())
                            .key(key)
                            .contentType(detected)
                            .contentLength(Files.size(temp))
                            .build(),
                    RequestBody.fromFile(temp));
            }
            return new Stored(key, detected, Files.size(temp), image, localProvider ? StoredFile.Provider.LOCAL : StoredFile.Provider.S3, sha256(temp));
        } finally {
            Files.deleteIfExists(temp);
        }
    }

    public InputStream read(String key) {
        if (key.startsWith("local:")) {
            try { return local.read(key.substring(6)); }
            catch (IOException exception) { throw new IllegalStateException("Không thể đọc file local.", exception); }
        }
        ResponseInputStream<GetObjectResponse> result = s3.getObject(GetObjectRequest.builder()
                .bucket(properties.storage().bucket())
                .key(key)
                .build());
        return result;
    }

    public String signedGetUrl(String key, Duration duration) {
        if (key.startsWith("local:")) {
            long expiry = java.time.Instant.now().plus(duration).getEpochSecond();
            String payload = expiry + "." + Base64.getUrlEncoder().withoutPadding().encodeToString(key.getBytes(StandardCharsets.UTF_8));
            return "/api/local-files/" + payload + "." + sign(payload);
        }
        return presigner.presignGetObject(GetObjectPresignRequest.builder()
                .signatureDuration(duration)
                .getObjectRequest(GetObjectRequest.builder().bucket(properties.storage().bucket()).key(key).build())
                .build()).url().toString();
    }

    public void delete(String key) {
        if (key.startsWith("local:")) {
            try { local.delete(key.substring(6)); } catch (IOException ignored) { }
            return;
        }
        s3.deleteObject(DeleteObjectRequest.builder().bucket(properties.storage().bucket()).key(key).build());
    }

    public record Stored(String key, String mediaType, long size, boolean image, StoredFile.Provider provider, String sha256) {}

    public SignedContent openSigned(String token) {
        int split = token.lastIndexOf('.');
        if (split < 1) throw new ApiException(HttpStatus.FORBIDDEN, "INVALID_FILE_TOKEN", "Liên kết file không hợp lệ.");
        String payload=token.substring(0,split), signature=token.substring(split+1);
        if (!java.security.MessageDigest.isEqual(sign(payload).getBytes(StandardCharsets.US_ASCII),signature.getBytes(StandardCharsets.US_ASCII)))
            throw new ApiException(HttpStatus.FORBIDDEN,"INVALID_FILE_TOKEN","Liên kết file không hợp lệ.");
        String[] parts=payload.split("\\.",2);
        if(parts.length!=2||Long.parseLong(parts[0])<java.time.Instant.now().getEpochSecond()) throw new ApiException(HttpStatus.FORBIDDEN,"FILE_TOKEN_EXPIRED","Liên kết file đã hết hạn.");
        String key=new String(Base64.getUrlDecoder().decode(parts[1]),StandardCharsets.UTF_8);
        if(!key.startsWith("local:")) throw new ApiException(HttpStatus.FORBIDDEN,"INVALID_FILE_TOKEN","Liên kết file không hợp lệ.");
        try {
            Path path=local.resolve(key.substring(6));
            return new SignedContent(Files.newInputStream(path),tika.detect(path),Files.size(path));
        } catch(IOException|IllegalArgumentException exception){throw new ApiException(HttpStatus.NOT_FOUND,"FILE_NOT_FOUND","Không tìm thấy file.");}
    }

    private String sign(String value) {
        try { Mac mac=Mac.getInstance("HmacSHA256");mac.init(new SecretKeySpec(signingKey,"HmacSHA256"));return Base64.getUrlEncoder().withoutPadding().encodeToString(mac.doFinal(value.getBytes(StandardCharsets.UTF_8))); }
        catch(Exception exception){throw new IllegalStateException(exception);}
    }
    private String extension(String name){if(name==null)return "";int index=name.lastIndexOf('.');String value=index<0?"":name.substring(index);return value.matches("\\.[A-Za-z0-9]{1,8}")?value:"";}
    private String sha256(Path path) throws IOException {try{java.security.MessageDigest digest=java.security.MessageDigest.getInstance("SHA-256");try(InputStream input=Files.newInputStream(path)){byte[] buffer=new byte[8192];for(int read;(read=input.read(buffer))>=0;)if(read>0)digest.update(buffer,0,read);}return java.util.HexFormat.of().formatHex(digest.digest());}catch(java.security.NoSuchAlgorithmException impossible){throw new IllegalStateException(impossible);}}
    public record SignedContent(InputStream input,String mediaType,long size){}
}
