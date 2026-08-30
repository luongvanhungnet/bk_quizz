package com.genquiz.bk.storage;

import com.genquiz.bk.config.AppProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;

import java.net.URI;

@Configuration
public class StorageConfig {
    @Bean
    S3Client s3Client(AppProperties properties) {
        AppProperties.Storage storage = properties.storage();
        return S3Client.builder()
                .endpointOverride(URI.create(storage.endpoint()))
                .region(Region.of(storage.region()))
                .credentialsProvider(StaticCredentialsProvider.create(
                        AwsBasicCredentials.create(storage.accessKey(), storage.secretKey())))
                .serviceConfiguration(r2CompatibleConfiguration(storage))
                .build();
    }

    @Bean
    S3Presigner s3Presigner(AppProperties properties) {
        AppProperties.Storage storage = properties.storage();
        return S3Presigner.builder()
                .endpointOverride(URI.create(storage.endpoint()))
                .region(Region.of(storage.region()))
                .credentialsProvider(StaticCredentialsProvider.create(
                        AwsBasicCredentials.create(storage.accessKey(), storage.secretKey())))
                .serviceConfiguration(r2CompatibleConfiguration(storage))
                .build();
    }

    S3Configuration r2CompatibleConfiguration(AppProperties.Storage storage) {
        return S3Configuration.builder()
                .pathStyleAccessEnabled(storage.pathStyle())
                // R2 does not support the streaming SigV4/chunked encoding used by AWS SDK v2 by default.
                .chunkedEncodingEnabled(false)
                .build();
    }
}
