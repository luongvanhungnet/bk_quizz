package com.genquiz.bk.explore;

import com.genquiz.bk.attempt.AttemptRepository;
import com.genquiz.bk.common.error.ApiException;
import com.genquiz.bk.community.TopicBookmarkRepository;
import com.genquiz.bk.quiz.QuestionRepository;
import com.genquiz.bk.quiz.QuizRepository;
import com.genquiz.bk.quiz.QuizStatus;
import com.genquiz.bk.topic.Topic;
import com.genquiz.bk.topic.TopicRepository;
import com.genquiz.bk.topic.Visibility;
import com.genquiz.bk.user.UserRepository;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ExploreService {
    private final TopicRepository topics;
    private final QuizRepository quizzes;
    private final QuestionRepository questions;
    private final UserRepository users;
    private final AttemptRepository attempts;
    private final TopicBookmarkRepository bookmarks;

    public ExploreService(TopicRepository topics, QuizRepository quizzes, QuestionRepository questions,
                          UserRepository users, AttemptRepository attempts, TopicBookmarkRepository bookmarks) {
        this.topics = topics; this.quizzes = quizzes; this.questions = questions; this.users = users;
        this.attempts = attempts; this.bookmarks = bookmarks;
    }

    @Transactional(readOnly = true)
    public Page<ExploreDtos.TopicSummary> list(String query, String sort, int page, int limit) {
        String safeSort = "popular".equalsIgnoreCase(sort) ? "popular" : "recent";
        return topics.findPublic(query == null ? "" : query.trim(), safeSort, PageRequest.of(page - 1, limit))
                .map(this::summary);
    }

    @Transactional(readOnly = true)
    public ExploreDtos.TopicDetail detail(UUID topicId) {
        Topic topic = requirePublic(topicId);
        var publicQuizzes = quizzes.findByTopicIdAndStatusAndVisibilityAndModerationStatusAndDeletedAtIsNullOrderByPublishedAtDesc(
                topicId, QuizStatus.PUBLISHED, Visibility.PUBLIC, com.genquiz.bk.common.ModerationStatus.ACTIVE).stream()
                .map(q -> new ExploreDtos.QuizSummary(q.getId(), q.getTitle(), q.getDifficulty(), q.getCognitiveMode(),
                        q.getDurationMinutes(), questions.countByQuizId(q.getId()), q.getPublishedAt()))
                .toList();
        return new ExploreDtos.TopicDetail(summary(topic), publicQuizzes);
    }

    public ExploreDtos.TopicSummary summary(Topic topic) {
        String owner = users.findByIdAndDeletedAtIsNull(topic.getOwnerId()).map(u -> u.getUsername()).orElse("Người dùng");
        return new ExploreDtos.TopicSummary(topic.getId(), topic.getTitle(), topic.getDescription(),
                topic.getOwnerId(), owner,
                quizzes.countByTopicIdAndStatusAndVisibilityAndDeletedAtIsNull(topic.getId(), QuizStatus.PUBLISHED, Visibility.PUBLIC),
                attempts.countDistinctLearnersByTopic(topic.getId()), bookmarks.countByTopicId(topic.getId()),
                topic.getPublishedAt());
    }

    public Topic requirePublic(UUID topicId) {
        Topic topic = topics.findByIdAndDeletedAtIsNull(topicId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "TOPIC_NOT_FOUND", "Không tìm thấy chủ đề."));
        if (!topic.isPubliclyVisible()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "TOPIC_NOT_FOUND", "Không tìm thấy chủ đề.");
        }
        return topic;
    }
}
