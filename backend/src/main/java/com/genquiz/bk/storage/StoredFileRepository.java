package com.genquiz.bk.storage;
import java.util.*; import org.springframework.data.domain.*; import org.springframework.data.jpa.repository.*; import org.springframework.data.repository.query.Param;
public interface StoredFileRepository extends JpaRepository<StoredFile,UUID>{
 Optional<StoredFile> findByIdAndDeletedAtIsNull(UUID id);
 @Query("select coalesce(sum(f.sizeBytes),0) from StoredFile f where f.ownerId=:owner and f.deletedAt is null and f.status=com.genquiz.bk.storage.StoredFile.Status.READY") long usedBytes(@Param("owner") UUID owner);
 @Query("select coalesce(sum(f.sizeBytes),0) from StoredFile f where f.deletedAt is null and f.status=com.genquiz.bk.storage.StoredFile.Status.READY") long totalReadyBytes();
 @Query("select f from StoredFile f where (:q='' or lower(f.originalName) like lower(concat('%',:q,'%'))) and (:status is null or f.status=:status) order by f.createdAt desc") Page<StoredFile> search(@Param("q") String q,@Param("status") StoredFile.Status status,Pageable pageable);
}
