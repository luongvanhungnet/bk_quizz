package com.genquiz.bk.topic;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
public interface TopicRepository extends JpaRepository<Topic, UUID> {
    Page<Topic> findByOwnerIdAndDeletedAtIsNull(UUID ownerId, Pageable pageable);
    Optional<Topic> findByIdAndDeletedAtIsNull(UUID id);
    List<Topic> findByOwnerIdAndStatusAndDeletedAtIsNull(UUID ownerId, TopicStatus status);
    long countByOwnerIdAndDeletedAtIsNull(UUID ownerId);
    List<Topic> findTop5ByOwnerIdAndDeletedAtIsNullOrderByUpdatedAtDesc(UUID ownerId);

    @Query(value = """
            select t.* from topics t
            where t.visibility = 'PUBLIC' and t.status = 'PUBLISHED' and t.moderation_status = 'ACTIVE' and t.deleted_at is null
              and (:search = '' or t.title ilike concat('%', :search, '%')
                   or coalesce(t.description, '') ilike concat('%', :search, '%'))
            order by
              case when :sort = 'popular' then
                (select count(*) from topic_bookmarks b where b.topic_id = t.id)
              end desc,
              t.published_at desc
            """,
            countQuery = """
            select count(*) from topics t
            where t.visibility = 'PUBLIC' and t.status = 'PUBLISHED' and t.moderation_status = 'ACTIVE' and t.deleted_at is null
              and (:search = '' or t.title ilike concat('%', :search, '%')
                   or coalesce(t.description, '') ilike concat('%', :search, '%'))
            """, nativeQuery = true)
    Page<Topic> findPublic(@Param("search") String search, @Param("sort") String sort, Pageable pageable);
}
