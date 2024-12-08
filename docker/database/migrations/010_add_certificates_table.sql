CREATE TABLE IF NOT EXISTS certificates (
    id SERIAL PRIMARY KEY,
    subject_dn VARCHAR(255),
    subject_cn VARCHAR(255),
    subject_an VARCHAR(255)[],
    valid_date TIMESTAMP,
    expiry_date TIMESTAMP,
    issuer_dn VARCHAR(255),
    issuer_cn VARCHAR(255),
    issuer_org VARCHAR(255),
    serial VARCHAR(255),
    fingerprint_hash VARCHAR(255),
    program_id INTEGER REFERENCES programs(id) ON DELETE CASCADE NOT NULL,
    discovered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE certificates ADD CONSTRAINT unique_certificate_serial_cn UNIQUE (subject_cn, serial);
