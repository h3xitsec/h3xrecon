CREATE TABLE IF NOT EXISTS nuclei (
    id SERIAL PRIMARY KEY,
    url VARCHAR(1024) NOT NULL,
    matched_at VARCHAR(1024) NOT NULL,
    type VARCHAR(50),
    ip VARCHAR(45),
    port INTEGER,
    template_path VARCHAR(255),
    template_id VARCHAR(100),
    template_name VARCHAR(255),
    severity VARCHAR(20),
    program_id INTEGER REFERENCES programs(id) ON DELETE CASCADE NOT NULL,
    discovered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE nuclei ADD CONSTRAINT unique_nuclei_url_matched_at UNIQUE (url, template_id);