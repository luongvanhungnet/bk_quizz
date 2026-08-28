package com.genquiz.bk.storage;

import com.genquiz.bk.config.AppProperties;
import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.HealthIndicator;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.HeadBucketRequest;

@Component("r2Storage")
@ConditionalOnProperty(name = "bkquiz.storage.provider", havingValue = "s3")
public class R2StorageHealthIndicator implements HealthIndicator {
    private final S3Client s3;
    private final String bucket;

    public R2StorageHealthIndicator(S3Client s3, AppProperties properties) {
        this.s3 = s3;
        this.bucket = properties.storage().bucket();
    }

    @Override
    public Health health() {
        try {
            s3.headBucket(HeadBucketRequest.builder().bucket(bucket).build());
            return Health.up().withDetail("provider", "cloudflare-r2").withDetail("bucket", bucket).build();
        } catch (RuntimeException exception) {
            return Health.down()
                    .withDetail("provider", "cloudflare-r2")
                    .withDetail("bucket", bucket)
                    .withDetail("error", exception.getClass().getSimpleName())
                    .build();
        }
    }
}
