package com.knowledgeassistant.task;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

// autoApply = true means Hibernate will automatically use this for ANY TaskStatus field globally
@Converter(autoApply = true)
public class TaskStatusConverter implements AttributeConverter<TaskStatus, String> {

    @Override
    public String convertToDatabaseColumn(TaskStatus attribute) {
        if (attribute == null) {
            return null;
        }
        // Writes "in-progress" to PostgreSQL, satisfying the CHECK constraint
        return attribute.getValue();
    }

    @Override
    public TaskStatus convertToEntityAttribute(String dbData) {
        if (dbData == null) {
            return null;
        }
        // Reads "in-progress" from PostgreSQL and maps it back to in_progress
        return TaskStatus.fromValue(dbData);
    }
}