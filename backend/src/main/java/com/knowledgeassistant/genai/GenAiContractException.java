package com.knowledgeassistant.genai;

import com.knowledgeassistant.common.DomainException;
import com.knowledgeassistant.common.ErrorCode;
import org.springframework.http.HttpStatus;

/**
 * Spring and the GenAI service disagree about the contract. <strong>This side's bug.</strong>
 *
 * <p>A {@code 422} from Python means Spring sent something malformed. The frontend never
 * reaches that service and Spring validated the user's input before calling, so a 422 is a
 * defect in this client — not user error. INTEGRATION_CONTRACT.md is explicit: log it as a
 * Spring defect and return a server error. It must <strong>never</strong> be relayed to the
 * user as "your input was invalid", because the user's input was fine.
 *
 * <p>This is the drift BACKLOG.md 3a predicts: Spring's client is hand-written against the
 * FastAPI spec and nothing compares them. When this exception fires, the spec moved.
 */
public class GenAiContractException extends DomainException {
    public GenAiContractException(String message) {
        super(message, ErrorCode.INTERNAL_ERROR, HttpStatus.INTERNAL_SERVER_ERROR);
    }
}
