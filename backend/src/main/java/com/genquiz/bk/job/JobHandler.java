package com.genquiz.bk.job;

public interface JobHandler {
    JobType type();
    String handle(Job job) throws Exception;
}

