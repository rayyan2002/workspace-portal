package com.knowledgeassistant.task;

import com.knowledgeassistant.common.TaskNotFoundException;
import com.knowledgeassistant.common.dto.PageResponse;
import com.knowledgeassistant.task.dto.TaskDto;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Service
public class TaskService {

    private final TaskRepository taskRepository;

    public TaskService(TaskRepository taskRepository) {
        this.taskRepository = taskRepository;
    }

    @Transactional(readOnly = true)
    public PageResponse<TaskDto> getTasks(UUID userId, TaskStatus status, Pageable pageable) {
        var page = (status != null)
                ? taskRepository.findByOwnerAndStatus(userId, status, pageable)
                : taskRepository.findByOwner(userId, pageable);

        return PageResponse.from(page, TaskDto::from);
    }

    @Transactional
    public TaskDto updateStatus(UUID taskId, TaskStatus newStatus, UUID userId) {
        // Ownership is in the WHERE clause: another user's task never loads, so there is
        // no window in which we hold an entity we are not entitled to mutate.
        Task task = taskRepository.findByIdAndOwner(taskId, userId)
                .orElseThrow(() -> new TaskNotFoundException("Task not found: " + taskId));

        task.setStatus(newStatus);

        if (newStatus == TaskStatus.done) {
            task.setCompletedAt(Instant.now());
        } else {
            task.setCompletedAt(null);
        }

        // Dirty checking will persist this, but an explicit save is fine too
        taskRepository.save(task);
        return TaskDto.from(task);
    }
}
