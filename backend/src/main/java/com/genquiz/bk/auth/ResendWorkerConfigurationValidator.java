package com.genquiz.bk.auth;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "bkquiz.jobs.worker-enabled", havingValue = "true")
public class ResendWorkerConfigurationValidator implements ApplicationRunner {
    private final ResendMailClient client;
    public ResendWorkerConfigurationValidator(ResendMailClient client) { this.client = client; }
    @Override public void run(ApplicationArguments args) { client.requireConfiguration(); }
}
