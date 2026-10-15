package com.bluestone.knowledge_assistant;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

/**
 * The context boots.
 *
 * <p><strong>{@code @ActiveProfiles("test")} was added on Day 17, and this test is what
 * caught the need for it.</strong> It was the only {@code @SpringBootTest} in the suite
 * without a profile, so when "no profile" stopped being treated as development it became the
 * one context that refused to start — correctly, and for exactly the reason the change
 * exists. A deployment that forgets {@code SPRING_PROFILES_ACTIVE} is in the same state this
 * test was in, and it used to boot on the signing key published in this repository.
 *
 * <p>Every other test already declared the profile. This one had been running against
 * whatever the defaults happened to be, which is a weaker thing to assert than it looks.
 */
@SpringBootTest
@ActiveProfiles("test")
class KnowledgeAssistantApplicationTests {

	@Test
	void contextLoads() {
	}

}
