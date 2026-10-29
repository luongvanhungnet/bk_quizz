package com.genquiz.bk.analytics;

import com.genquiz.bk.common.error.ApiException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Date;
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AdminAnalyticsService {
    private final JdbcTemplate jdbc;
    private final AnalyticsProperties properties;
    private final AnalyticsAggregationService aggregation;

    public AdminAnalyticsService(JdbcTemplate jdbc, AnalyticsProperties properties,
                                 AnalyticsAggregationService aggregation) {
        this.jdbc = jdbc;
        this.properties = properties;
        this.aggregation = aggregation;
    }

    @Transactional(readOnly = true)
    public AdminAnalyticsDtos.Overview overview(LocalDate from, LocalDate to) {
        Range range = range(from, to);
        long dau = distinctUsers(range.to(), range.to());
        long wau = distinctUsers(range.to().minusDays(6), range.to());
        long mau = distinctUsers(range.to().minusDays(29), range.to());
        var totals = jdbc.queryForMap("""
            select coalesce(sum(new_users),0) new_users,coalesce(sum(activated_users),0) activated_users,
              coalesce(sum(ai_quizzes_generated),0) quiz_generations,
              coalesce(sum(quizzes_completed),0) quizzes_completed,
              coalesce(sum(ai_requests),0) ai_requests
            from daily_platform_metrics where metric_date between ? and ?
            """, range.start(), range.end());
        BigDecimal cost = decimal("select coalesce(sum(actual_cost),0) from daily_ai_metrics where metric_date between ? and ?", range);
        long generations = number(totals.get("quiz_generations"));
        long aiRequests = number(totals.get("ai_requests"));
        long quota = scalarLong("select coalesce(sum(event_count),0) from daily_security_metrics where metric_date between ? and ? and event_type in ('AI_QUOTA_EXHAUSTED','RATE_LIMIT_TRIGGERED')", range);
        long blocked = scalarLong("select coalesce(sum(event_count),0) from daily_security_metrics where metric_date between ? and ? and event_type in ('RATE_LIMIT_TRIGGERED','BOT_CHALLENGE_FAILED','ABNORMAL_AI_USAGE')", range);
        long highRisk = scalarLong("select count(*) from account_reputations where risk_score>=0.60 or service_level in ('RESTRICTED','BLOCKED')");
        return new AdminAnalyticsDtos.Overview(dau, wau, mau, number(totals.get("new_users")),
                number(totals.get("activated_users")), generations, number(totals.get("quizzes_completed")),
                aiRequests, cost, ratio(cost, dau), ratio(cost, generations),
                aiRequests == 0 ? 0 : (double) quota / aiRequests, blocked, highRisk,
                points("active_users", range), points("new_users", range),
                new AdminAnalyticsDtos.Availability(false, "SUBSCRIPTION_DATA_NOT_AVAILABLE"));
    }

    @Transactional(readOnly = true)
    public AdminAnalyticsDtos.UserAnalytics users(LocalDate from, LocalDate to) {
        Range range = range(from, to);
        return new AdminAnalyticsDtos.UserAnalytics(points("new_users", range), points("activated_users", range),
                retention(range, 1), retention(range, 7), retention(range, 30));
    }

    @Transactional(readOnly = true)
    public AdminAnalyticsDtos.AiAnalytics ai(LocalDate from, LocalDate to, int topLimit) {
        Range range = range(from, to);
        List<AdminAnalyticsDtos.MoneyPoint> dailyCost = jdbc.query("""
                select metric_date,coalesce(sum(actual_cost),0) value from daily_ai_metrics
                where metric_date between ? and ? group by metric_date order by metric_date
                """, (rs, i) -> new AdminAnalyticsDtos.MoneyPoint(rs.getObject(1, LocalDate.class), rs.getBigDecimal(2)), range.start(), range.end());
        List<AdminAnalyticsDtos.Point> dailyRequests = jdbc.query("""
                select metric_date,coalesce(sum(request_count),0) value from daily_ai_metrics
                where metric_date between ? and ? group by metric_date order by metric_date
                """, (rs, i) -> new AdminAnalyticsDtos.Point(rs.getObject(1, LocalDate.class), rs.getLong(2)), range.start(), range.end());
        List<AdminAnalyticsDtos.AiModelUsage> models = jdbc.query("""
                select provider,model,sum(request_count),sum(success_count),sum(failure_count),
                  sum(input_tokens),sum(output_tokens),sum(estimated_cost),sum(actual_cost)
                from daily_ai_metrics where metric_date between ? and ? group by provider,model
                order by sum(actual_cost) desc
                """, (rs, i) -> new AdminAnalyticsDtos.AiModelUsage(rs.getString(1),rs.getString(2),rs.getLong(3),
                    rs.getLong(4),rs.getLong(5),rs.getLong(6),rs.getLong(7),rs.getBigDecimal(8),rs.getBigDecimal(9)),
                range.start(), range.end());
        List<AdminAnalyticsDtos.CostUser> costUsers = jdbc.query("""
                select d.user_id,u.username,u.email,sum(d.ai_request_count),sum(d.ai_cost) cost
                from daily_user_metrics d join users u on u.id=d.user_id
                where d.metric_date between ? and ? group by d.user_id,u.username,u.email
                having sum(d.ai_cost)>0 order by cost desc limit ?
                """, (rs, i) -> new AdminAnalyticsDtos.CostUser(rs.getObject(1, UUID.class),rs.getString(2),
                    rs.getString(3),rs.getLong(4),rs.getBigDecimal(5)), range.start(), range.end(), Math.min(100, Math.max(1, topLimit)));
        BigDecimal total = decimal("select coalesce(sum(actual_cost),0) from daily_ai_metrics where metric_date between ? and ?", range);
        long requests = models.stream().mapToLong(AdminAnalyticsDtos.AiModelUsage::requests).sum();
        long failures = models.stream().mapToLong(AdminAnalyticsDtos.AiModelUsage::failures).sum();
        long quota = scalarLong("select coalesce(sum(event_count),0) from daily_security_metrics where metric_date between ? and ? and event_type='RATE_LIMIT_TRIGGERED'", range);
        return new AdminAnalyticsDtos.AiAnalytics(dailyCost,dailyRequests,models,costUsers,total,
                requests==0?0:(double)failures/requests, requests+quota==0?0:(double)quota/(requests+quota), topOnePercentShare(range));
    }

    @Transactional(readOnly = true)
    public AdminAnalyticsDtos.SecurityAnalytics security(LocalDate from, LocalDate to) {
        Range range = range(from, to);
        List<AdminAnalyticsDtos.SecurityMetric> events = jdbc.query("""
                select event_type,sum(event_count),sum(prevented_cost) from daily_security_metrics
                where metric_date between ? and ? group by event_type order by sum(event_count) desc
                """, (rs,i)->new AdminAnalyticsDtos.SecurityMetric(rs.getString(1),rs.getLong(2),rs.getBigDecimal(3)), range.start(),range.end());
        List<AdminAnalyticsDtos.Distribution> levels = jdbc.query("select service_level,count(*) from account_reputations group by service_level order by service_level",
                (rs,i)->new AdminAnalyticsDtos.Distribution(rs.getString(1),rs.getLong(2)));
        List<AdminAnalyticsDtos.Distribution> bands = jdbc.query("""
                select case when risk_score>=.9 then 'CRITICAL' when risk_score>=.6 then 'HIGH'
                  when risk_score>=.3 then 'MEDIUM' else 'LOW' end,count(*)
                from account_reputations group by 1 order by 1
                """,(rs,i)->new AdminAnalyticsDtos.Distribution(rs.getString(1),rs.getLong(2)));
        long rate = count(events,"RATE_LIMIT_TRIGGERED");
        long failed = count(events,"LOGIN_FAILED");
        long suspicious = count(events,"SUSPICIOUS_REGISTRATION");
        long restricted = distribution(levels,"RESTRICTED");
        long blockedAccounts = distribution(levels,"BLOCKED");
        BigDecimal prevented = events.stream().map(AdminAnalyticsDtos.SecurityMetric::preventedCost).reduce(BigDecimal.ZERO,BigDecimal::add);
        return new AdminAnalyticsDtos.SecurityAnalytics(rate,rate,failed,suspicious,restricted,blockedAccounts,
                restricted+blockedAccounts,prevented,events,levels,bands);
    }

    @Transactional
    public void recompute(LocalDate from, LocalDate to) {
        Range range = range(from,to);
        aggregation.recompute(range.from(), range.to());
    }

    private List<AdminAnalyticsDtos.RetentionPoint> retention(Range range, int day) {
        LocalDate lastCohort = range.to().minusDays(day);
        if (lastCohort.isBefore(range.from())) return List.of();
        return jdbc.query("""
            with cohorts as (
              select (occurred_at at time zone 'UTC')::date cohort_date,user_id
              from product_events where event_type='USER_REGISTERED' and user_id is not null
                and (occurred_at at time zone 'UTC')::date between ? and ?
            ) select cohort_date,count(*) cohort_size,
              count(*) filter(where exists(select 1 from daily_user_metrics d
                where d.user_id=cohorts.user_id and d.metric_date=cohort_date+?)) retained
              from cohorts group by cohort_date order by cohort_date
            """, (rs,i)->{
                long size=rs.getLong(2), retained=rs.getLong(3);
                return new AdminAnalyticsDtos.RetentionPoint(rs.getObject(1,LocalDate.class),size,retained,day,
                        size==0?0:(double)retained/size);
            }, range.start(), Date.valueOf(lastCohort), day);
    }

    private List<AdminAnalyticsDtos.Point> points(String column, Range range) {
        if (!List.of("active_users","new_users","activated_users").contains(column)) throw new IllegalArgumentException("Invalid metric");
        return jdbc.query("select metric_date,"+column+" from daily_platform_metrics where metric_date between ? and ? order by metric_date",
                (rs,i)->new AdminAnalyticsDtos.Point(rs.getObject(1,LocalDate.class),rs.getLong(2)),range.start(),range.end());
    }

    private long distinctUsers(LocalDate from, LocalDate to) {
        return jdbc.queryForObject("select count(distinct user_id) from daily_user_metrics where metric_date between ? and ?",
                Long.class,Date.valueOf(from),Date.valueOf(to));
    }
    private BigDecimal decimal(String sql, Range range) {
        BigDecimal value=jdbc.queryForObject(sql,BigDecimal.class,range.start(),range.end());
        return value==null?BigDecimal.ZERO:value;
    }
    private long scalarLong(String sql, Range range) { Long value=jdbc.queryForObject(sql,Long.class,range.start(),range.end());return value==null?0:value; }
    private long scalarLong(String sql) { Long value=jdbc.queryForObject(sql,Long.class);return value==null?0:value; }
    private double topOnePercentShare(Range range) {
        List<BigDecimal> costs=jdbc.queryForList("""
            select sum(ai_cost) cost from daily_user_metrics where metric_date between ? and ?
            group by user_id having sum(ai_cost)>0 order by cost desc
            """,BigDecimal.class,range.start(),range.end());
        return topOnePercentCostShare(costs);
    }
    static double topOnePercentCostShare(List<BigDecimal> values) {
        if(values==null||values.isEmpty()) return 0;
        List<BigDecimal> sorted=values.stream().filter(java.util.Objects::nonNull)
                .filter(v->v.signum()>0).sorted(java.util.Comparator.reverseOrder()).toList();
        if(sorted.isEmpty()) return 0;
        int top=Math.max(1,(int)Math.ceil(sorted.size()*.01));
        BigDecimal total=sorted.stream().reduce(BigDecimal.ZERO,BigDecimal::add);
        BigDecimal leading=sorted.stream().limit(top).reduce(BigDecimal.ZERO,BigDecimal::add);
        return total.signum()==0?0:leading.divide(total,12,RoundingMode.HALF_UP).doubleValue();
    }
    private Range range(LocalDate from, LocalDate to) {
        LocalDate end=to==null?LocalDate.now():to;
        LocalDate start=from==null?end.minusDays(29):from;
        long days=ChronoUnit.DAYS.between(start,end)+1;
        if(days<1||days>properties.maxRangeDays()) throw new ApiException(HttpStatus.BAD_REQUEST,"ANALYTICS_DATE_RANGE_INVALID",
                "Khoảng ngày phải từ 1 đến "+properties.maxRangeDays()+" ngày.");
        return new Range(start,end,Date.valueOf(start),Date.valueOf(end));
    }
    private static BigDecimal ratio(BigDecimal value,long denominator){return denominator==0?BigDecimal.ZERO:value.divide(BigDecimal.valueOf(denominator),6,RoundingMode.HALF_UP);}
    private static long number(Object value){return value instanceof Number n?n.longValue():0;}
    private static long count(List<AdminAnalyticsDtos.SecurityMetric> list,String type){return list.stream().filter(v->v.eventType().equals(type)).mapToLong(AdminAnalyticsDtos.SecurityMetric::count).sum();}
    private static long distribution(List<AdminAnalyticsDtos.Distribution> list,String value){return list.stream().filter(v->v.value().equals(value)).mapToLong(AdminAnalyticsDtos.Distribution::count).sum();}
    private record Range(LocalDate from,LocalDate to,Date start,Date end) {}
}
