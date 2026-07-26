package com.genquiz.bk.source;

import com.genquiz.bk.job.Job;
import com.genquiz.bk.job.JobHandler;
import com.genquiz.bk.job.JobType;
import com.genquiz.bk.job.JobDeferredException;
import com.genquiz.bk.rag.RagClient;
import com.genquiz.bk.rag.RagServiceException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Component;

@Component
public class RagIndexPollHandler implements JobHandler {
    private final SourceService sources;
    private final RagClient rag;
    private final ConcurrentMap<java.util.UUID, Integer> pollCounts = new ConcurrentHashMap<>();

    public RagIndexPollHandler(SourceService sources, RagClient rag) {
        this.sources = sources; this.rag = rag;
    }
    @Override public JobType type() { return JobType.RAG_INDEX_POLL; }

    @Override public String handle(Job job) {
        SourceDocument source = sources.getForWorker(job.getResourceId());
        var remote = rag.job(source.getOwnerId(), source.getRagJobId());
        sources.updateRagProgress(source.getId(), remote.progress(), remote.step());
        if ("FAILED".equals(remote.status()) || "CANCELLED".equals(remote.status())) {
            pollCounts.remove(job.getId());
            throw new RagServiceException(
                    remote.errorCode() == null ? "RAG_INDEXING_FAILED" : remote.errorCode(),
                    remote.errorMessage() == null ? "Không thể lập chỉ mục tài liệu." : remote.errorMessage(),
                    false, null, null, null);
        }
        if (!"SUCCEEDED".equals(remote.status())) {
            int poll = pollCounts.merge(job.getId(), 1, Integer::sum);
            long[] delays = {2, 3, 5, 10};
            throw new JobDeferredException(Duration.ofSeconds(delays[Math.min(poll - 1, delays.length - 1)]));
        }
        pollCounts.remove(job.getId());
        sources.beginRagSync(source.getId());
        var document = rag.document(source.getOwnerId(), source.getRagDocumentId());
        var chunks = new ArrayList<com.genquiz.bk.rag.RagDtos.Chunk>();
        for (int page = 1; ; page++) {
            var response = rag.chunks(source.getOwnerId(), source.getRagDocumentId(), page);
            chunks.addAll(response.items());
            if (page >= response.pagination().totalPages()) break;
        }
        sources.completeRagIndex(source.getId(), document, chunks);
        return "{\"sourceDocumentId\":\"" + source.getId() + "\",\"chunks\":" + chunks.size() + "}";
    }
}
