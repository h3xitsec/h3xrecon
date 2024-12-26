-- Component Logging Tables

-- Worker execution logs
CREATE TABLE IF NOT EXISTS worker_logs (
    id SERIAL PRIMARY KEY,
    execution_id UUID NOT NULL,
    component_id VARCHAR(255) NOT NULL,
    function_name VARCHAR(255) NOT NULL,
    program_id INTEGER NOT NULL REFERENCES programs(id),
    target TEXT NOT NULL,
    parameters JSONB NOT NULL,
    status VARCHAR(50) NOT NULL, -- 'started', 'completed', 'failed'
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(execution_id, status)
);

-- Job processor logs
CREATE TABLE IF NOT EXISTS jobprocessor_logs (
    id SERIAL PRIMARY KEY,
    component_id VARCHAR(255) NOT NULL,
    message_id VARCHAR(255) NOT NULL,
    message_type VARCHAR(255) NOT NULL,
    program_id INTEGER NOT NULL REFERENCES programs(id),
    message_data JSONB NOT NULL,
    processing_result JSONB,
    actions_taken JSONB,
    status VARCHAR(50) NOT NULL, -- 'received', 'processed', 'failed'
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP WITH TIME ZONE
);

-- Data processor logs
CREATE TABLE IF NOT EXISTS dataprocessor_logs (
    id SERIAL PRIMARY KEY,
    component_id VARCHAR(255) NOT NULL,
    data_type VARCHAR(255) NOT NULL,
    program_id INTEGER NOT NULL REFERENCES programs(id),
    operation_type VARCHAR(255) NOT NULL, -- 'insert', 'update', 'trigger_job'
    data JSONB NOT NULL,
    result JSONB,
    status VARCHAR(50) NOT NULL, -- 'started', 'completed', 'failed'
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS worker_logs_execution_id_idx ON worker_logs(execution_id);
CREATE INDEX IF NOT EXISTS worker_logs_component_id_idx ON worker_logs(component_id);
CREATE INDEX IF NOT EXISTS worker_logs_program_id_idx ON worker_logs(program_id);
CREATE INDEX IF NOT EXISTS worker_logs_function_name_idx ON worker_logs(function_name);

CREATE INDEX IF NOT EXISTS jobprocessor_logs_component_id_idx ON jobprocessor_logs(component_id);
CREATE INDEX IF NOT EXISTS jobprocessor_logs_program_id_idx ON jobprocessor_logs(program_id);
CREATE INDEX IF NOT EXISTS jobprocessor_logs_message_type_idx ON jobprocessor_logs(message_type);

CREATE INDEX IF NOT EXISTS dataprocessor_logs_component_id_idx ON dataprocessor_logs(component_id);
CREATE INDEX IF NOT EXISTS dataprocessor_logs_program_id_idx ON dataprocessor_logs(program_id);
CREATE INDEX IF NOT EXISTS dataprocessor_logs_data_type_idx ON dataprocessor_logs(data_type);
CREATE INDEX IF NOT EXISTS dataprocessor_logs_operation_type_idx ON dataprocessor_logs(operation_type); 