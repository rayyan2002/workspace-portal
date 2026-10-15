package com.bluestone.knowledge_assistant.action;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class ActionTypeConverter implements AttributeConverter<ActionType, String> {

    @Override
    public String convertToDatabaseColumn(ActionType attribute) {
        if (attribute == null) {
            return null;
        }
        return attribute.getValue(); // Writes "create-task" to PostgreSQL
    }

    @Override
    public ActionType convertToEntityAttribute(String dbData) {
        if (dbData == null) {
            return null;
        }
        return ActionType.fromValue(dbData); // Reuses the method we made for @JsonCreator
    }
}