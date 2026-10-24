package com.knowledgeassistant.task;

import java.util.stream.Collectors;
import java.util.Map;
import com.knowledgeassistant.action.ActionProposalRepository;
import com.knowledgeassistant.action.ActionProposal;
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
    private final ActionProposalRepository actionProposalRepository;

    public TaskService(TaskRepository taskRepository, ActionProposalRepository actionProposalRepository) {
        this.taskRepository = taskRepository;
        this.actionProposalRepository = actionProposalRepository;
    }

    @Transactional(readOnly = true)
    public PageResponse<TaskDto> getTasks(UUID userId, TaskStatus status, Pageable pageable) {
        var page = (status != null)
                ? taskRepository.findByOwnerAndStatus(userId, status, pageable)
                : taskRepository.findByOwner(userId, pageable);

        // ONE extra query for the page, resolving action -> proposal -> message so a task
        // can link to the prompt that proposed it. Tasks predating V23 have no
        // source_action_id and resolve to null, which the frontend reads as "session only".
        Map<String, UUID> messageIds = actionProposalRepository
                .findByActionIdIn(page.getContent().stream()
                        .map(Task::getSourceActionId)
                        .filter(java.util.Objects::nonNull)
                        .toList())
                .stream()
                .collect(Collectors.toMap(ActionProposal::getActionId,
                        ActionProposal::getMessageId, (a, b) -> a));

        return PageResponse.from(page, task -> TaskDto.from(task,
                task.getSourceActionId() == null
                        ? null : messageIds.get(task.getSourceActionId())));
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
