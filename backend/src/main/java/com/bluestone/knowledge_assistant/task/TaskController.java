package com.bluestone.knowledge_assistant.task;

import com.bluestone.knowledge_assistant.security.annotation.CurrentUserId;
import com.bluestone.knowledge_assistant.common.PageRequestFactory;
import com.bluestone.knowledge_assistant.common.dto.PageResponse;
import com.bluestone.knowledge_assistant.task.dto.TaskDto;
import com.bluestone.knowledge_assistant.task.dto.TaskStatusUpdateRequest;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/tasks")
public class TaskController {

    private final TaskService taskService;

    public TaskController(TaskService taskService) {
        this.taskService = taskService;
    }

    @Operation(summary = "List the caller's tasks (paged)")
    @GetMapping
    public ResponseEntity<PageResponse<TaskDto>> getTasks(@RequestParam(required = false) TaskStatus status,
                                                          @RequestParam(required = false) Integer page,
                                                          @RequestParam(required = false) Integer size,
                                                          @CurrentUserId UUID userId) {
        return ResponseEntity.ok(taskService.getTasks(userId, status, PageRequestFactory.of(page, size)));
    }

    @Operation(summary = "Update a task's status")
    @PatchMapping("/{taskId}")
    public ResponseEntity<TaskDto> updateStatus(
            @PathVariable UUID taskId,
            @Valid @RequestBody TaskStatusUpdateRequest request,
            @CurrentUserId UUID userId) {
        return ResponseEntity.ok(taskService.updateStatus(taskId, request.status(), userId));
    }
}
