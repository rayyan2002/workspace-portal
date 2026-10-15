package com.knowledgeassistant.action;

import com.knowledgeassistant.action.dto.ActionRequest;
import com.knowledgeassistant.action.dto.ActionResult;
import com.knowledgeassistant.action.dto.ActionAuditDto;
import com.knowledgeassistant.common.PageRequestFactory;
import com.knowledgeassistant.common.dto.PageResponse;
import com.knowledgeassistant.security.annotation.CurrentUserId;
import com.knowledgeassistant.task.dto.TaskDto;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api")
public class ActionController {

    private final ActionService actionService;

    public ActionController(ActionService actionService) {
        this.actionService = actionService;
    }

    @Operation(summary = "Process an AI Action (Governance)")
    @io.swagger.v3.oas.annotations.parameters.RequestBody(
            content = @Content(
                    mediaType = "application/json",
                    examples = {
                            @ExampleObject(
                                    name = "1. Approve Task",
                                    summary = "Executes the creation of a runway task",
                                    value = """
                    {
                      "actionId": "act-123",
                      "sessionId": "33333333-3333-3333-3333-333333333333",
                      "decision": "approved",
                      "type": "create-task",
                      "payload": {
                        "title": "Review runway schedule",
                        "priority": "high"
                      }
                    }
                    """
                            ),
                            @ExampleObject(
                                    name = "2. Reject Task",
                                    summary = "Audits the rejection but skips execution",
                                    value = """
                    {
                      "actionId": "act-124",
                      "sessionId": "33333333-3333-3333-3333-333333333333",
                      "decision": "rejected",
                      "type": "create-task",
                      "payload": {
                        "title": "Invalid request",
                        "priority": "low"
                      }
                    }
                    """
                            )
                    }
            )
    )
    @PostMapping("/ai/actions")
    public ResponseEntity<ActionResult> handle(@Valid @RequestBody ActionRequest request,
                                               @CurrentUserId UUID userId) {
        ActionResult result = actionService.processAction(request, userId);
        return ResponseEntity.ok(result);
    }

    @GetMapping("/actions/audit")
    public ResponseEntity<PageResponse<ActionAuditDto>> getAuditTrail(
            @RequestParam(required = false) Integer page,
            @RequestParam(required = false) Integer size,
            @CurrentUserId UUID userId) {
        return ResponseEntity.ok(actionService.getAuditTrail(userId, PageRequestFactory.of(page, size)));
    }


}