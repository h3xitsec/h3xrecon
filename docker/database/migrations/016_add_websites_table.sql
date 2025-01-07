CREATE TABLE IF NOT EXISTS websites (
    id SERIAL PRIMARY KEY,
    url VARCHAR(1024) UNIQUE NOT NULL,
    host VARCHAR(255) DEFAULT NULL,
    port INTEGER DEFAULT NULL,
    scheme VARCHAR(50) DEFAULT NULL,
    techs TEXT[] DEFAULT NULL,
    program_id INTEGER REFERENCES programs(id) ON DELETE CASCADE NOT NULL,
    favicon_hash VARCHAR(255) DEFAULT NULL,
    favicon_url VARCHAR(1024) DEFAULT NULL,
    discovered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP 
);

ALTER TABLE websites ADD CONSTRAINT unique_websites_program_id_url UNIQUE (program_id, url);

INSERT INTO websites (url, port, scheme, techs, program_id, discovered_at, host)
SELECT 
    url,
    port,
    scheme,
    tech,
    program_id,
    discovered_at,
    REGEXP_REPLACE(REGEXP_REPLACE(url, '^https?://([^/]+).*$', '\1'), ':[0-9]+$', '') as host
FROM urls;

CREATE TABLE IF NOT EXISTS websites_paths (
    id SERIAL PRIMARY KEY,
    website_id INTEGER REFERENCES websites(id) ON DELETE CASCADE NOT NULL,
    path character varying(1024) DEFAULT NULL::character varying,
    final_path character varying(1024) DEFAULT NULL::character varying,
    techs text[],
    response_time character varying(50) DEFAULT NULL::character varying,
    lines integer,
    title character varying(1024) DEFAULT NULL::character varying,
    words integer,
    method character varying(10) DEFAULT NULL::character varying,
    scheme character varying(50) DEFAULT NULL::character varying,
    status_code integer,
    content_type character varying(255) DEFAULT NULL::character varying,
    content_length integer,
    chain_status_codes integer[],
    page_type character varying(50),
    body_preview text,
    resp_header_hash character varying(255),
    resp_body_hash character varying(255),
    program_id INTEGER REFERENCES programs(id) ON DELETE CASCADE NOT NULL
);

ALTER TABLE websites_paths ADD CONSTRAINT unique_websites_paths_website_id_path UNIQUE (website_id, path);

INSERT INTO websites_paths (website_id, path, final_path, techs, response_time, lines, title, words, method, scheme, status_code, content_type, content_length, chain_status_codes, page_type, body_preview, program_id)
SELECT 
    w.id as website_id,
    CASE 
        WHEN u.url ~ '^https?://[^/]+/?$' THEN '/'
        ELSE REGEXP_REPLACE(u.url, '^https?://[^/]+', '')
    END as path,
    REGEXP_REPLACE(u.final_url, '^https?://[^/]+', '') as final_path,
    u.tech,
    u.response_time,
    u.lines,
    u.title,
    u.words,
    u.method,
    u.scheme,
    u.status_code,
    u.content_type,
    u.content_length,
    u.chain_status_codes,
    u.page_type,
    u.body_preview,
    w.program_id
FROM urls u
JOIN websites w ON u.url = w.url;

INSERT INTO websites_paths (website_id, path, techs, response_time, lines, title, words, method, scheme, status_code, content_type, content_length, page_type, body_preview, program_id)
SELECT 
    w.id as website_id,
    CASE 
        WHEN u.final_url ~ '^https?://[^/]+/?$' THEN '/'
        ELSE REGEXP_REPLACE(u.final_url, '^https?://[^/]+', '')
    END as path,
    u.tech,
    u.response_time,
    u.lines,
    u.title,
    u.words,
    u.method,
    u.scheme,
    u.status_code,
    u.content_type,
    u.content_length,
    u.page_type,
    u.body_preview,
    w.program_id
FROM urls u
JOIN websites w ON u.url = w.url
ON CONFLICT (website_id, path) DO NOTHING;

ALTER TABLE certificates RENAME COLUMN url_id TO website_id;
ALTER TABLE screenshots RENAME COLUMN url_id TO website_id;

DELETE FROM websites_paths WHERE path IS NULL;