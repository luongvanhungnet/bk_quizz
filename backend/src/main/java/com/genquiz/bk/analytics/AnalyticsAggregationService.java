package com.genquiz.bk.analytics;

import java.sql.Date;
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneOffset;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AnalyticsAggregationService {
    private final JdbcTemplate jdbc;
    private final Clock clock;

    @org.springframework.beans.factory.annotation.Autowired
    public AnalyticsAggregationService(JdbcTemplate jdbc) {
        this(jdbc, Clock.systemUTC());
    }

    AnalyticsAggregationService(JdbcTemplate jdbc, Clock clock) {
        this.jdbc = jdbc;
        this.clock = clock;
    }

    @Transactional
    public void recompute(LocalDate from, LocalDate to) {
        if (from == null || to == null || to.isBefore(from)) throw new IllegalArgumentException("Khoảng ngày không hợp lệ.");
        Date start = Date.valueOf(from);
        Date end = Date.valueOf(to);
        jdbc.update("delete from daily_security_metrics where metric_date between ? and ?", start, end);
        jdbc.update("delete from daily_ai_metrics where metric_date between ? and ?", start, end);
        jdbc.update("delete from daily_platform_metrics where metric_date between ? and ?", start, end);
        jdbc.update("delete from daily_user_metrics where metric_date between ? and ?", start, end);

        jdbc.update("""
            insert into daily_user_metrics(metric_date,user_id,event_count,quiz_count,ai_request_count,ai_cost)
            select (occurred_at at time zone 'UTC')::date, user_id, count(*),
                   count(*) filter (where event_type in ('QUIZ_CREATED','AI_QUIZ_GENERATED','QUIZ_COMPLETED')),
                   count(*) filter (where event_type='AI_REQUEST_COMPLETED'),
                   coalesce(sum(case when event_type='AI_REQUEST_COMPLETED'
                     and coalesce(properties->>'actualCost',properties->>'estimatedCost','') ~ '^[0-9]+(\\.[0-9]+)?$'
                     then coalesce(properties->>'actualCost',properties->>'estimatedCost')::numeric else 0 end),0)
            from product_events
            where user_id is not null and (occurred_at at time zone 'UTC')::date between ? and ?
            group by 1,2
            """, start, end);

        jdbc.update("""
            insert into daily_platform_metrics(metric_date,active_users,new_users,activated_users,
              quizzes_created,ai_quizzes_generated,quizzes_completed,documents_uploaded,
              documents_ingested,ai_requests,updated_at)
            select d::date, coalesce(count(distinct p.user_id) filter (where p.event_type not in ('USER_REGISTERED')),0),
              count(*) filter(where p.event_type='USER_REGISTERED'),
              count(*) filter(where p.event_type='USER_ACTIVATED'),
              count(*) filter(where p.event_type='QUIZ_CREATED'),
              count(*) filter(where p.event_type='AI_QUIZ_GENERATED'),
              count(*) filter(where p.event_type='QUIZ_COMPLETED'),
              count(*) filter(where p.event_type='DOCUMENT_UPLOADED'),
              count(*) filter(where p.event_type='DOCUMENT_INGESTED'),
              count(*) filter(where p.event_type='AI_REQUEST_COMPLETED'), current_timestamp
            from generate_series(?::date, ?::date, interval '1 day') d
            left join product_events p on (p.occurred_at at time zone 'UTC')::date=d::date
            group by d order by d
            """, start, end);

        jdbc.update("""
            insert into daily_ai_metrics(metric_date,provider,model,request_count,success_count,
              failure_count,input_tokens,output_tokens,estimated_cost,actual_cost,updated_at)
            select (occurred_at at time zone 'UTC')::date,
              coalesce(nullif(properties->>'provider',''),'unknown'),
              coalesce(nullif(properties->>'model',''),'unknown'), count(*),
              count(*) filter(where properties->>'status'='SUCCEEDED'),
              count(*) filter(where properties->>'status'='FAILED'), 0, 0,
              coalesce(sum(case when coalesce(properties->>'estimatedCost','') ~ '^[0-9]+(\\.[0-9]+)?$'
                then (properties->>'estimatedCost')::numeric else 0 end),0),
              coalesce(sum(case when coalesce(properties->>'actualCost','') ~ '^[0-9]+(\\.[0-9]+)?$'
                then (properties->>'actualCost')::numeric else 0 end),0), current_timestamp
            from product_events where event_type='AI_REQUEST_COMPLETED'
              and (occurred_at at time zone 'UTC')::date between ? and ? group by 1,2,3
            """, start, end);

        jdbc.update("""
            insert into daily_security_metrics(metric_date,event_type,event_count,prevented_cost,updated_at)
            select metric_date,event_type,sum(event_count),sum(prevented_cost),current_timestamp from (
              select (created_at at time zone 'UTC')::date metric_date,event_type,count(*) event_count,
                coalesce(sum(case when coalesce(metadata->>'preventedCost','') ~ '^[0-9]+(\\.[0-9]+)?$'
                  then (metadata->>'preventedCost')::numeric else 0 end),0) prevented_cost
              from risk_events where (created_at at time zone 'UTC')::date between ? and ? group by 1,2
              union all
              select (created_at at time zone 'UTC')::date,action,count(*),0
              from audit_logs where action='LOGIN_FAILED'
                and (created_at at time zone 'UTC')::date between ? and ? group by 1,2
            ) x group by metric_date,event_type
            """, start, end, start, end);
    }

    public void recomputeRecent() {
        LocalDate today = LocalDate.now(clock.withZone(ZoneOffset.UTC));
        recompute(today.minusDays(1), today);
    }
}
