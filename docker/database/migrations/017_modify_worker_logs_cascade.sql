-- Modify recon_logs (formerly worker_logs)
ALTER TABLE recon_logs DROP CONSTRAINT worker_logs_program_id_fkey;
ALTER TABLE recon_logs
    ADD CONSTRAINT recon_logs_program_id_fkey
    FOREIGN KEY (program_id)
    REFERENCES programs(id)
    ON DELETE CASCADE;

-- Modify parsing_logs (formerly jobprocessor_logs)
ALTER TABLE parsing_logs DROP CONSTRAINT jobprocessor_logs_program_id_fkey;
ALTER TABLE parsing_logs
    ADD CONSTRAINT parsing_logs_program_id_fkey
    FOREIGN KEY (program_id)
    REFERENCES programs(id)
    ON DELETE CASCADE;

-- Modify data_logs (formerly dataprocessor_logs)
ALTER TABLE data_logs DROP CONSTRAINT dataprocessor_logs_program_id_fkey;
ALTER TABLE data_logs
    ADD CONSTRAINT data_logs_program_id_fkey
    FOREIGN KEY (program_id)
    REFERENCES programs(id)
    ON DELETE CASCADE; 