package com.genquiz.bk.topic;

import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import com.genquiz.bk.security.VerifiedAccountGuard;
import com.genquiz.bk.classroom.ClassroomTopicShareRepository;

@Service
public class TopicService {
    private final TopicRepository topics;
    private final Clock clock;
    private final VerifiedAccountGuard verifiedAccounts;
    private final ClassroomTopicShareRepository classroomShares;

    @Autowired
    public TopicService(TopicRepository topics, VerifiedAccountGuard verifiedAccounts,
                        ClassroomTopicShareRepository classroomShares) {
        this(topics, verifiedAccounts, classroomShares, Clock.systemUTC());
    }

    TopicService(TopicRepository topics, VerifiedAccountGuard verifiedAccounts, Clock clock) {
        this(topics, verifiedAccounts, null, clock);
    }

    TopicService(TopicRepository topics, VerifiedAccountGuard verifiedAccounts,
                 ClassroomTopicShareRepository classroomShares, Clock clock) {
        this.topics = topics;
        this.verifiedAccounts = verifiedAccounts;
        this.classroomShares = classroomShares;
        this.clock = clock;
    }

    @Transactional
    public Topic create(UUID actorId, TopicDtos.SaveRequest request) {
        return topics.save(new Topic(actorId, request.title(), request.description(), request.visibility()));
    }

    @Transactional(readOnly = true)
    public Page<Topic> listOwned(UUID actorId, Pageable pageable) {
        return topics.findByOwnerIdAndDeletedAtIsNull(actorId, pageable);
    }

    @Transactional(readOnly = true)
    public Topic getOwned(UUID actorId, UUID topicId) {
        Topic topic = requireActive(topicId);
        requireOwner(topic, actorId);
        return topic;
    }

    @Transactional(readOnly = true)
    public Topic getAccessible(UUID actorId, UUID topicId) {
        Topic topic = requireActive(topicId);
        boolean sharedWithClassroom = classroomShares != null
                && classroomShares.canActiveMemberAccess(topicId, actorId);
        if (!topic.isOwnedBy(actorId) && !topic.isPubliclyVisible() && !sharedWithClassroom) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Bạn không có quyền xem chủ đề này");
        }
        return topic;
    }

    @Transactional
    public Topic update(UUID actorId, UUID topicId, TopicDtos.SaveRequest request) {
        Topic topic = getOwned(actorId, topicId);
        topic.update(request.title(), request.description(), request.visibility());
        return topic;
    }

    @Transactional
    public Topic publish(UUID actorId, UUID topicId) {
        verifiedAccounts.require(actorId);
        Topic topic = getOwned(actorId, topicId);
        topic.publish(Instant.now(clock));
        return topic;
    }

    @Transactional
    public void delete(UUID actorId, UUID topicId, boolean hasDependentLearningData) {
        Topic topic = getOwned(actorId, topicId);
        // Soft deletion is the safe default; asynchronous retention cleanup may hard-delete unused drafts later.
        topic.softDelete();
    }

    private Topic requireActive(UUID topicId) {
        return topics.findByIdAndDeletedAtIsNull(topicId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Không tìm thấy chủ đề"));
    }

    private static void requireOwner(Topic topic, UUID actorId) {
        if (!topic.isOwnedBy(actorId)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Bạn không có quyền chỉnh sửa chủ đề này");
        }
    }
}
