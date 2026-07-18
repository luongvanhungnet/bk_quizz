package com.genquiz.bk.storage;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.ByteArrayInputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class LocalFileStorageTest {
    @TempDir Path root;

    @Test
    void storesOnlyRelativePathsAndReadsBytesAfterRecreatingTheStorage() throws Exception {
        LocalFileStorage storage = new LocalFileStorage(root, root.resolve("tmp"));
        String path = storage.store("SOURCE", ".txt", new ByteArrayInputStream("hello".getBytes()));

        assertThat(Path.of(path).isAbsolute()).isFalse();
        assertThat(path).doesNotContain("..");
        assertThat(new LocalFileStorage(root, root.resolve("tmp")).read(path).readAllBytes())
                .isEqualTo("hello".getBytes());
        assertThat(Files.exists(root.resolve(path))).isTrue();
    }

    @Test
    void rejectsTraversalWhenReading() {
        LocalFileStorage storage = new LocalFileStorage(root, root.resolve("tmp"));
        assertThatThrownBy(() -> storage.read("../secret.txt"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
