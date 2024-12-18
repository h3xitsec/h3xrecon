DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'ips' 
        AND column_name = 'cloud_provider'
    ) THEN
        ALTER TABLE ips ADD COLUMN cloud_provider VARCHAR(50);
    END IF;
END $$;
