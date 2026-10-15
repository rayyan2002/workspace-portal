package com.bluestone.knowledge_assistant.health;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {

    // Record acting as our localized DTO for the health response
    public record HealthStatus(String status) {}

    @GetMapping("/api/health")
    public HealthStatus checkHealth() {
        return new HealthStatus("UP");
    }
}