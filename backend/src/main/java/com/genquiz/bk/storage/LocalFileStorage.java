package com.genquiz.bk.storage;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.LocalDate;
import java.util.Locale;
import java.util.UUID;

public class LocalFileStorage {
    private final Path root;
    private final Path temporaryRoot;

    public LocalFileStorage(Path root, Path temporaryRoot) {
        this.root = root.toAbsolutePath().normalize();
        this.temporaryRoot = temporaryRoot.toAbsolutePath().normalize();
    }

    public String store(String purpose, String extension, InputStream input) throws IOException {
        Files.createDirectories(root);
        Files.createDirectories(temporaryRoot);
        String safePurpose = purpose.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9_-]", "-");
        String safeExtension = extension != null && extension.matches("\\.[a-zA-Z0-9]{1,8}")
                ? extension.toLowerCase(Locale.ROOT) : "";
        LocalDate now = LocalDate.now();
        Path relative = Path.of(safePurpose, String.valueOf(now.getYear()), "%02d".formatted(now.getMonthValue()),
                UUID.randomUUID() + safeExtension);
        Path target = resolve(relative.toString());
        Files.createDirectories(target.getParent());
        Path staged = Files.createTempFile(temporaryRoot, "upload-", ".tmp");
        try {
            Files.copy(input, staged, StandardCopyOption.REPLACE_EXISTING);
            try {
                Files.move(staged, target, StandardCopyOption.ATOMIC_MOVE);
            } catch (java.nio.file.AtomicMoveNotSupportedException ignored) {
                Files.move(staged, target, StandardCopyOption.REPLACE_EXISTING);
            }
            return root.relativize(target).toString().replace('\\', '/');
        } finally {
            Files.deleteIfExists(staged);
        }
    }

    public InputStream read(String relativePath) throws IOException {
        return Files.newInputStream(resolve(relativePath));
    }

    public void delete(String relativePath) throws IOException {
        Files.deleteIfExists(resolve(relativePath));
    }

    public Path resolve(String relativePath) {
        if (relativePath == null || relativePath.isBlank() || Path.of(relativePath).isAbsolute()) {
            throw new IllegalArgumentException("Đường dẫn file không hợp lệ.");
        }
        Path resolved = root.resolve(relativePath).normalize();
        if (!resolved.startsWith(root)) throw new IllegalArgumentException("Đường dẫn file không hợp lệ.");
        return resolved;
    }
}
