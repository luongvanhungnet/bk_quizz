package com.genquiz.bk.source;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import com.genquiz.bk.job.Job;
import com.genquiz.bk.job.JobHandler;
import com.genquiz.bk.job.JobType;
import org.apache.tika.metadata.Metadata;
import org.apache.tika.parser.AutoDetectParser;
import org.apache.tika.sax.BodyContentHandler;
import org.springframework.stereotype.Component;

import java.io.InputStream;

@Component
public class SourceIngestionHandler implements JobHandler {
    private final SourceObjectStorage storage;
    private final SourceService sources;
    private final ObjectMapper mapper;
    public SourceIngestionHandler(SourceObjectStorage storage, SourceService sources, ObjectMapper mapper) {
        this.storage = storage; this.sources = sources; this.mapper = mapper;
    }
    @Override public JobType type() { return JobType.SOURCE_INGESTION; }
    @Override public String handle(Job job) throws Exception {
        JsonNode payload = mapper.readTree(job.getPayload());
        String objectKey = payload.path("objectKey").stringValue();
        BodyContentHandler body = new BodyContentHandler(-1);
        try (InputStream input = storage.read(objectKey)) {
            new AutoDetectParser().parse(input, body, new Metadata());
        }
        String text = body.toString().replace('\u0000', ' ').trim();
        if (text.length() < 10) throw new IllegalArgumentException("Không trích xuất được nội dung có ý nghĩa từ tài liệu.");
        sources.completeExtraction(job.getResourceId(), text);
        return mapper.writeValueAsString(java.util.Map.of("sourceDocumentId", job.getResourceId(),
                "characters", text.length()));
    }
}
