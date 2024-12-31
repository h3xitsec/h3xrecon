CREATE TABLE IF NOT EXISTS screenshots (
    id SERIAL PRIMARY KEY,
    program_id INT NOT NULL,
    filepath VARCHAR(255) NOT NULL,
    md5_hash VARCHAR(32) NOT NULL,
    url_id INT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE screenshots ADD CONSTRAINT unique_screenshots_program_id_path UNIQUE (program_id, filepath);