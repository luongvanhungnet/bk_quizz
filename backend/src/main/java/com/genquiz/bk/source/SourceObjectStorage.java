package com.genquiz.bk.source;

import java.io.IOException;
import java.io.InputStream;

/** Adapter point for the S3-compatible MinIO/production implementation. */
public interface SourceObjectStorage {
    StoredObject scanAndStore(String requestedName, String declaredContentType, long sizeBytes, InputStream data)
            throws IOException;
    InputStream read(String objectKey) throws IOException;
    void delete(String objectKey);

    record StoredObject(String objectKey, String detectedContentType, String provider, String sha256) {}
}
