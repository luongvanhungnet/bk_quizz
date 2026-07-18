package com.genquiz.bk.classroom;
import java.util.List; import java.util.Optional; import java.util.UUID; import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
public interface ClassroomTopicShareRepository extends JpaRepository<ClassroomTopicShare,UUID>{
 Optional<ClassroomTopicShare> findByIdAndClassroomId(UUID id,UUID classroomId);
 Optional<ClassroomTopicShare> findByClassroomIdAndTopicIdAndRevokedAtIsNull(UUID classroomId,UUID topicId);
 List<ClassroomTopicShare> findByClassroomIdAndRevokedAtIsNullOrderByCreatedAtDesc(UUID classroomId);
 boolean existsByTopicIdAndRevokedAtIsNullAndClassroomIdIn(UUID topicId,java.util.Collection<UUID> classroomIds);

 @Query(value="""
   select exists(
     select 1 from classroom_topic_shares s
     join classroom_members m on m.classroom_id=s.classroom_id
     join classrooms c on c.id=s.classroom_id
     where s.topic_id=:topicId and s.revoked_at is null
       and m.user_id=:userId and m.status='ACTIVE' and c.status='ACTIVE'
   )
   """, nativeQuery=true)
 boolean canActiveMemberAccess(@Param("topicId") UUID topicId,@Param("userId") UUID userId);
}
