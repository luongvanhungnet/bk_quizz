package com.genquiz.bk.community;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.explore.ExploreDtos;
import com.genquiz.bk.explore.ExploreService;
import com.genquiz.bk.topic.Topic;
import com.genquiz.bk.topic.Visibility;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpStatus;

@ExtendWith(MockitoExtension.class)
class TopicBookmarkServiceTest {
    @Mock TopicBookmarkRepository repository;
    @Mock ExploreService explore;

    @Test
    void bookmarkIsIdempotentAndReturnsRealTopicSummary() {
        UUID userId = UUID.randomUUID();
        UUID topicId = UUID.randomUUID();
        Topic topic = new Topic(UUID.randomUUID(), "Mạng máy tính", "TCP/IP", Visibility.PUBLIC);
        var summary = new ExploreDtos.TopicSummary(topicId, "Mạng máy tính", "TCP/IP",
                UUID.randomUUID(), "student", 2, 4, 1, Instant.now());
        TopicBookmark existing = new TopicBookmark(userId, topicId, Instant.now());
        when(explore.requirePublic(topicId)).thenReturn(topic);
        when(explore.summary(topic)).thenReturn(summary);
        when(repository.findByUserIdAndTopicId(userId, topicId)).thenReturn(Optional.of(existing));

        var result = new TopicBookmarkService(repository, explore).bookmark(userId, topicId);

        assertThat(result.topic()).isEqualTo(summary);
        assertThat(result.savedAt()).isEqualTo(existing.getCreatedAt());
        verify(repository, never()).save(any());
    }

    @Test
    void privateTopicCannotBeBookmarked() {
        UUID topicId = UUID.randomUUID();
        when(explore.requirePublic(topicId)).thenThrow(
                new ApiException(HttpStatus.NOT_FOUND, "TOPIC_NOT_FOUND", "Không tìm thấy chủ đề."));

        assertThatThrownBy(() -> new TopicBookmarkService(repository, explore)
                .bookmark(UUID.randomUUID(), topicId)).isInstanceOf(ApiException.class);
        verify(repository, never()).findByUserIdAndTopicId(any(), any());
    }
}
