package com.genquiz.bk.classroom;
import java.time.Instant; import java.util.List; import java.util.Optional; import java.util.UUID;
import org.springframework.data.domain.Pageable; import org.springframework.data.jpa.repository.JpaRepository; import org.springframework.data.jpa.repository.Query; import org.springframework.data.repository.query.Param;
public interface ClassroomMessageRepository extends JpaRepository<ClassroomMessage,UUID>{
 Optional<ClassroomMessage> findByIdAndClassroomId(UUID id,UUID classroomId);
 List<ClassroomMessage> findByClassroomIdOrderByCreatedAtDescIdDesc(UUID classroomId, Pageable pageable);
 @Query(value="""
   select * from classroom_messages
   where classroom_id=:classroomId and (created_at < :before or (created_at = :before and id < :beforeId))
   order by created_at desc, id desc
   """,nativeQuery=true)
 List<ClassroomMessage> pageBefore(@Param("classroomId") UUID classroomId,@Param("before") Instant before,
                                   @Param("beforeId") UUID beforeId,Pageable pageable);
 long countByClassroomIdAndCreatedAtAfter(UUID classroomId,Instant after);
}
