DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'services_ip_fkey' 
        AND contype = 'f'
    ) THEN
        ALTER TABLE services DROP CONSTRAINT IF EXISTS services_ip_fkey;

        ALTER TABLE services
        ADD CONSTRAINT services_ip_fkey
        FOREIGN KEY (ip) REFERENCES ips(id) ON DELETE CASCADE;
    END IF;
END $$;