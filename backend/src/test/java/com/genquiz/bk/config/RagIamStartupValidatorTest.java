package com.genquiz.bk.config;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;
import org.springframework.mock.env.MockEnvironment;

class RagIamStartupValidatorTest {
    private static final RagProperties RAG = new RagProperties(
            true, "https://rag.example.run.app", "internal-key",
            Duration.ofSeconds(5), Duration.ofSeconds(30));

    @Test
    void productionRequiresIamForEnabledRag() {
        var validator = new RagIamStartupValidator(
                RAG, new RagIamProperties(false, ""), production());

        assertThatThrownBy(() -> validator.run(new DefaultApplicationArguments()))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("RAG_IAM_ENABLED");
    }

    @Test
    void productionAcceptsHttpsAudienceWhenIamIsEnabled() {
        var validator = new RagIamStartupValidator(
                RAG,
                new RagIamProperties(true, "https://rag.example.run.app/"),
                production());

        assertThatCode(() -> validator.run(new DefaultApplicationArguments()))
                .doesNotThrowAnyException();
    }

    @Test
    void localDevelopmentKeepsInternalKeyOnlyMode() {
        var validator = new RagIamStartupValidator(
                RAG, new RagIamProperties(false, ""), new MockEnvironment());

        assertThatCode(() -> validator.run(new DefaultApplicationArguments()))
                .doesNotThrowAnyException();
    }

    private MockEnvironment production() {
        return new MockEnvironment().withProperty("K_SERVICE", "bkquiz-api");
    }
}
