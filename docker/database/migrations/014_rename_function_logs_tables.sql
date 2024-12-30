-- Rename component logging tables
ALTER TABLE worker_logs RENAME TO recon_logs;
ALTER TABLE jobprocessor_logs RENAME TO parsing_logs;
ALTER TABLE dataprocessor_logs RENAME TO data_logs;
