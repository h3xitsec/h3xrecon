CREATE TABLE IF NOT EXISTS program_scopes_domains (
    id SERIAL PRIMARY KEY,
    program_id INTEGER REFERENCES programs(id) ON DELETE CASCADE,
    domain VARCHAR(255) NOT NULL,
    wildcard BOOLEAN DEFAULT FALSE,
    regex TEXT DEFAULT NULL
);

ALTER TABLE program_scopes_domains ADD CONSTRAINT unique_program_domain_regex UNIQUE (program_id, domain, regex);