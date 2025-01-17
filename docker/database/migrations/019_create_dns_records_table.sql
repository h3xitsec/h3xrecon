CREATE TABLE IF NOT EXISTS dns_records (
    id SERIAL PRIMARY KEY,
    domain_id INTEGER REFERENCES domains(id) ON DELETE CASCADE,
    program_id INTEGER REFERENCES programs(id) ON DELETE CASCADE,
    hostname TEXT NOT NULL,
    ttl INTEGER NOT NULL,
    dns_class VARCHAR(255) NOT NULL,
    dns_type VARCHAR(255) NOT NULL,
    value TEXT NOT NULL,
    discovered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE dns_records ADD CONSTRAINT unique_domain_record_type_value UNIQUE (domain_id, hostname, dns_type, value);