package com.genquiz.bk.storage;

import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.security.CurrentUser;
import com.genquiz.bk.user.User;
import com.genquiz.bk.user.UserRepository;
import com.genquiz.bk.user.dto.UserDto;
import org.apache.tika.Tika;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import software.amazon.awssdk.services.s3.model.S3Exception;

import javax.imageio.ImageIO;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Set;
import java.util.UUID;

@Service
public class AvatarService {
    private static final Logger log = LoggerFactory.getLogger(AvatarService.class);
    private static final long MAX_BYTES = 5L * 1024 * 1024;
    private static final Set<String> ALLOWED = Set.of("image/jpeg", "image/png", "image/webp");

    private final CurrentUser current;
    private final UserRepository users;
    private final StoredFileRepository files;
    private final ClamAvScanner scanner;
    private final AvatarObjectStorage objectStorage;
    private final Path temporaryRoot;
    private final long quotaBytes;

    public AvatarService(CurrentUser current, UserRepository users, StoredFileRepository files,
                         ClamAvScanner scanner, AvatarObjectStorage objectStorage,
                         @Value("${bkquiz.storage.local-temp:./data/tmp}") String temp,
                         @Value("${bkquiz.storage.user-quota-bytes:2147483648}") long quotaBytes) {
        this.current = current;
        this.users = users;
        this.files = files;
        this.scanner = scanner;
        this.objectStorage = objectStorage;
        this.temporaryRoot = Path.of(temp).toAbsolutePath().normalize();
        this.quotaBytes = quotaBytes;
    }

    @Transactional
    public UserDto upload(MultipartFile upload) {
        User user = current.require();
        if (upload == null || upload.isEmpty()) throw invalid("AVATAR_REQUIRED", "Vui lòng chọn ảnh đại diện.");
        if (upload.getSize() > MAX_BYTES) throw invalid("AVATAR_TOO_LARGE", "Ảnh đại diện không được vượt quá 5 MB.");
        if (files.usedBytes(user.getId()) + upload.getSize() > quotaBytes) {
            throw new ApiException(HttpStatus.CONTENT_TOO_LARGE, "STORAGE_QUOTA_EXCEEDED", "Dung lượng lưu trữ của tài khoản đã hết.");
        }

        Path staged = null;
        String storedPath = null;
        StoredFile.Provider storedProvider = null;
        try {
            Files.createDirectories(temporaryRoot);
            staged = Files.createTempFile(temporaryRoot, "avatar-", ".upload");
            try (InputStream input = upload.getInputStream()) { Files.copy(input, staged, java.nio.file.StandardCopyOption.REPLACE_EXISTING); }
            String detected = new Tika().detect(staged);
            if (!ALLOWED.contains(detected)) throw invalid("INVALID_AVATAR_TYPE", "Chỉ chấp nhận ảnh JPEG, PNG hoặc WebP.");
            scanner.requireClean(staged);

            Normalized normalized = normalize(staged, detected);
            AvatarObjectStorage.Stored object = objectStorage.store(
                    user.getId(), normalized.path(), normalized.extension(), normalized.mediaType());
            storedPath = object.path();
            storedProvider = object.provider();
            StoredFile stored = files.save(new StoredFile(user.getId(), StoredFile.Purpose.AVATAR,
                    storedProvider, storedPath, safeName(upload.getOriginalFilename()),
                    upload.getContentType(), normalized.mediaType(), Files.size(normalized.path()), sha256(normalized.path()), true));
            UUID previous = user.getAvatarFileId();
            user.setAvatarFileId(stored.getId());
            users.save(user);
            if (previous != null) files.findByIdAndDeletedAtIsNull(previous).ifPresent(StoredFile::softDelete);
            if (!normalized.path().equals(staged)) Files.deleteIfExists(normalized.path());
            return UserDto.from(user);
        } catch (ApiException exception) {
            deleteQuietly(storedProvider, storedPath);
            throw exception;
        } catch (IOException exception) {
            deleteQuietly(storedProvider, storedPath);
            throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "AVATAR_STORAGE_FAILED", "Không thể lưu ảnh đại diện.");
        } catch (RuntimeException exception) {
            deleteQuietly(storedProvider, storedPath);
            if (exception instanceof S3Exception s3Exception) {
                String errorCode = s3Exception.awsErrorDetails() == null
                        ? null : s3Exception.awsErrorDetails().errorCode();
                log.warn("Avatar object storage failed provider=s3 status={} errorCode={} requestId={}",
                        s3Exception.statusCode(), errorCode, s3Exception.requestId());
            } else {
                log.warn("Avatar object storage failed provider={} error={}", storedProvider,
                        exception.getClass().getSimpleName());
            }
            throw new ApiException(HttpStatus.BAD_GATEWAY, "AVATAR_STORAGE_FAILED", "Không thể kết nối kho lưu trữ ảnh đại diện.");
        } finally {
            if (staged != null) try { Files.deleteIfExists(staged); } catch (IOException ignored) { }
        }
    }

    @Transactional
    public UserDto delete() {
        User user = current.require();
        UUID previous = user.getAvatarFileId();
        user.setAvatarFileId(null);
        if (previous != null) files.findByIdAndDeletedAtIsNull(previous).ifPresent(StoredFile::softDelete);
        return UserDto.from(user);
    }

    @Transactional(readOnly = true)
    public AvatarContent read(UUID userId) {
        User user = users.findByIdAndDeletedAtIsNull(userId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "AVATAR_NOT_FOUND", "Không tìm thấy ảnh đại diện."));
        if (user.getAvatarFileId() == null) throw new ApiException(HttpStatus.NOT_FOUND, "AVATAR_NOT_FOUND", "Không tìm thấy ảnh đại diện.");
        StoredFile file = files.findByIdAndDeletedAtIsNull(user.getAvatarFileId())
                .filter(value -> value.getStatus() == StoredFile.Status.READY && value.isPublicAccess())
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "AVATAR_NOT_FOUND", "Không tìm thấy ảnh đại diện."));
        try { return new AvatarContent(objectStorage.read(file.getProvider(), file.getStoragePath()), file.getDetectedMediaType(), file.getSizeBytes(), file.getSha256()); }
        catch (IOException exception) { throw new ApiException(HttpStatus.NOT_FOUND, "AVATAR_NOT_FOUND", "Không tìm thấy ảnh đại diện."); }
    }

    private Normalized normalize(Path source, String detected) throws IOException {
        BufferedImage image = ImageIO.read(source.toFile());
        if (image == null) return new Normalized(source, detected, detected.equals("image/webp") ? ".webp" : ".img");
        int width = image.getWidth(), height = image.getHeight();
        double ratio = Math.min(1d, 512d / Math.max(width, height));
        int targetWidth = Math.max(1, (int) Math.round(width * ratio));
        int targetHeight = Math.max(1, (int) Math.round(height * ratio));
        BufferedImage outputImage = new BufferedImage(targetWidth, targetHeight, BufferedImage.TYPE_INT_RGB);
        Graphics2D graphics = outputImage.createGraphics();
        graphics.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BICUBIC);
        graphics.drawImage(image, 0, 0, targetWidth, targetHeight, null);
        graphics.dispose();
        Path output = Files.createTempFile(temporaryRoot, "avatar-normalized-", ".jpg");
        ImageIO.write(outputImage, "jpeg", output.toFile());
        return new Normalized(output, "image/jpeg", ".jpg");
    }

    private String sha256(Path path) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream input = Files.newInputStream(path)) { input.transferTo(new OutputStream() { public void write(int b) { digest.update((byte)b); } public void write(byte[] b,int o,int l){ digest.update(b,o,l); } }); }
            return HexFormat.of().formatHex(digest.digest());
        } catch (java.security.NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }

    private void deleteQuietly(StoredFile.Provider provider, String path) {
        if (provider == null || path == null) return;
        try { objectStorage.delete(provider, path); } catch (RuntimeException ignored) { }
    }
    private ApiException invalid(String code, String message) { return new ApiException(HttpStatus.UNPROCESSABLE_CONTENT, code, message); }
    private String safeName(String value) { return value == null || value.isBlank() ? "avatar" : Path.of(value).getFileName().toString(); }
    private record Normalized(Path path, String mediaType, String extension) { }
    public record AvatarContent(InputStream input, String mediaType, long size, String etag) { }
}
