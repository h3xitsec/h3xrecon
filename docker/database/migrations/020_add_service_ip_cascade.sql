-- First, drop the existing foreign key constraint
ALTER TABLE services DROP CONSTRAINT IF EXISTS services_ip_fkey;

-- Add the new foreign key constraint with ON DELETE CASCADE
ALTER TABLE services
    ADD CONSTRAINT services_ip_fkey
    FOREIGN KEY (ip)
    REFERENCES ips(id)
    ON DELETE CASCADE;