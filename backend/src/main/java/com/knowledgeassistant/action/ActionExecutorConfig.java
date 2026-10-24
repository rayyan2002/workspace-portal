package com.knowledgeassistant.action;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.SyncTaskExecutor;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

/**
 * The pool that runs approved actions after their decision has been acknowledged.
 *
 * <p>A dedicated executor rather than Spring's shared one, because these jobs are unlike
 * anything else on this service: a single summarise occupies a thread for 78-135 seconds
 * while it waits on a language model. Sharing a pool with short web work would let a handful
 * of approvals starve it.
 *
 * <p>BOUNDED, and the queue is bounded too. An unbounded queue would accept approvals
 * forever and surface as "nothing is happening" with no upper limit on how long; rejecting
 * the overflow lets the caller be told, which is the honest failure.
 */
@Configuration
public class ActionExecutorConfig {

    /**
     * Set {@code app.actions.async=false} to run approved actions on the calling thread.
     *
     * <p>A PROPERTY RATHER THAN A TEST-ONLY BEAN, because overriding a bean by name turned
     * out to depend on registration order — allowing the override simply let the production
     * definition win instead, silently, with the tests still green-looking until they
     * asserted on a row that said `running` forever. A property cannot land backwards.
     *
     * <p>It is also genuinely useful outside tests: a deployment that wants an approval to
     * fail loudly in the request rather than disappear into a pool can turn async off.
     */
    // No explicit destroyMethod: ThreadPoolTaskExecutor is a DisposableBean and shuts
    // itself down, while SyncTaskExecutor has no shutdown() to call at all.
    @Bean(name = "actionExecutor")
    public TaskExecutor actionExecutor(@Value("${app.actions.async:true}") boolean async) {
        if (!async) {
            return new SyncTaskExecutor();
        }
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("action-");
        // Finish what was accepted before the JVM goes away: a half-run summarise would
        // leave a `running` row that never resolves, which is the one state with no honest
        // reading. Bounded so a shutdown cannot hang indefinitely.
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(180);
        return executor;
    }
}
