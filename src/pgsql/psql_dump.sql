DO
$do$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_catalog.pg_roles
      WHERE  rolname = 'h3xrecon') THEN
      CREATE ROLE h3xrecon LOGIN PASSWORD 'h3xrecon';
   END IF;
END
$do$;

-- Grant necessary permissions to h3xrecon role
GRANT ALL PRIVILEGES ON DATABASE h3xrecon TO h3xrecon;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO h3xrecon;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO h3xrecon;

-- Drop existing tables if they exist
DROP TABLE IF EXISTS services;
DROP TABLE IF EXISTS urls;
DROP TABLE IF EXISTS ips;
DROP TABLE IF EXISTS domains;
DROP TABLE IF EXISTS program_cidrs;
DROP TABLE IF EXISTS program_scopes;
DROP TABLE IF EXISTS http_services;
DROP TABLE IF EXISTS programs;
DROP TABLE IF EXISTS function_logs;
DROP TABLE IF EXISTS logs;


CREATE TABLE out_of_scope_domains (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(255) NOT NULL UNIQUE,
    program_ids INTEGER[] NOT NULL,
    discovered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE function_logs (
    id SERIAL PRIMARY KEY,
    execution_id UUID NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    function_name VARCHAR(255) NOT NULL,
    target VARCHAR(255),
    program_id INTEGER
);

CREATE TABLE IF NOT EXISTS logs (
    id SERIAL PRIMARY KEY,
    execution_id UUID,
    timestamp TIMESTAMP WITH TIME ZONE,
    level VARCHAR(10),
    component VARCHAR(50),
    message TEXT,
    metadata JSONB
);

CREATE TABLE programs (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE program_scopes (
    id SERIAL PRIMARY KEY,
    program_id INTEGER REFERENCES programs(id) ON DELETE CASCADE,
    regex TEXT NOT NULL
);

CREATE TABLE program_cidrs (
    id SERIAL PRIMARY KEY,
    program_id INTEGER REFERENCES programs(id) ON DELETE CASCADE,
    cidr VARCHAR(255) NOT NULL
);

CREATE TABLE ips (
    id SERIAL PRIMARY KEY,
    ip VARCHAR(255) UNIQUE NOT NULL,
    ptr VARCHAR(1024) DEFAULT NULL,
    program_id INTEGER REFERENCES programs(id) ON DELETE CASCADE NOT NULL,
    discovered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE services (
    id SERIAL PRIMARY KEY,
    ip INTEGER DEFAULT NULL REFERENCES ips(id),
    port INTEGER DEFAULT NULL,
    protocol VARCHAR(255) DEFAULT NULL,
    service VARCHAR(255) DEFAULT NULL,
    program_id INTEGER REFERENCES programs(id) ON DELETE CASCADE NOT NULL,
    discovered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP 
);

ALTER TABLE services ADD CONSTRAINT unique_service_ip_port UNIQUE (ip, port);

CREATE TABLE urls (
    id SERIAL PRIMARY KEY,
    url VARCHAR(1024) UNIQUE NOT NULL,
    httpx_data JSONB,
    -- title VARCHAR(1024) DEFAULT NULL,
    -- chain_status_codes INTEGER[] DEFAULT NULL,
    -- status_code INTEGER DEFAULT NULL,
    -- final_url VARCHAR(1024) DEFAULT NULL,
    -- scheme VARCHAR(50) DEFAULT NULL,
    -- port INTEGER DEFAULT NULL,
    -- webserver VARCHAR(255) DEFAULT NULL,
    -- content_type VARCHAR(255) DEFAULT NULL,
    -- content_length INTEGER DEFAULT NULL,
    -- tech VARCHAR(1024)[] DEFAULT NULL,
    program_id INTEGER REFERENCES programs(id) ON DELETE CASCADE NOT NULL,
    discovered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE domains (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(255) UNIQUE NOT NULL,
    ips INTEGER[] DEFAULT NULL,
    cnames VARCHAR(1024)[] DEFAULT NULL,
    is_catchall BOOLEAN DEFAULT FALSE,
    program_id INTEGER REFERENCES programs(id) ON DELETE CASCADE NOT NULL,
    discovered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better query performance
CREATE INDEX idx_domains ON domains(domain);
CREATE INDEX idx_ips ON ips(ip);
CREATE INDEX idx_urls ON urls(url);
CREATE INDEX idx_function_logs_execution_id ON function_logs(execution_id);
CREATE INDEX idx_function_logs_timestamp ON function_logs(timestamp);
CREATE INDEX idx_function_logs_function_name ON function_logs(function_name);
CREATE INDEX idx_function_logs_program_id ON function_logs(program_id);
CREATE INDEX idx_domains_program ON domains(program_id, domain);
CREATE INDEX idx_ips_program ON ips(program_id, ip);
CREATE INDEX idx_urls_program ON urls(program_id, url);
CREATE INDEX idx_out_of_scope_domains ON out_of_scope_domains(domain);
CREATE INDEX idx_out_of_scope_domains_gin ON out_of_scope_domains USING GIN (program_ids);

-- Create built-in functions
CREATE OR REPLACE FUNCTION get_domains_for_program(program_name VARCHAR)
RETURNS TABLE (
    domain VARCHAR,
    ips INTEGER[],
    cnames VARCHAR[],
    discovered_at TIMESTAMP WITH TIME ZONE
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT d.domain, d.ips, d.cnames, d.discovered_at
    FROM domains d
    JOIN programs p ON d.program_id = p.id
    WHERE p.name = program_name
    ORDER BY d.discovered_at DESC;
END;
$$;

CREATE OR REPLACE FUNCTION get_ips_for_domain(target_domain VARCHAR)
RETURNS TABLE (
    ip VARCHAR,
    ptr VARCHAR,
    discovered_at TIMESTAMP WITH TIME ZONE
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT i.ip, i.ptr, i.discovered_at
    FROM ips i
    JOIN domains d ON i.id = ANY(d.ips)
    WHERE d.domain = target_domain
    ORDER BY i.discovered_at DESC;
END;
$$;

CREATE OR REPLACE FUNCTION get_urls_for_program(program_name VARCHAR)
RETURNS TABLE (
    url VARCHAR,
    title VARCHAR,
    status_code INTEGER,
    webserver VARCHAR,
    tech VARCHAR[],
    discovered_at TIMESTAMP WITH TIME ZONE
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT u.url, u.title, u.status_code, u.webserver, u.tech, u.discovered_at
    FROM urls u
    JOIN programs p ON u.program_id = p.id
    WHERE p.name = program_name
    ORDER BY u.discovered_at DESC;
END;
$$;

CREATE OR REPLACE FUNCTION get_recent_discoveries(days_back INTEGER)
RETURNS TABLE (
    type VARCHAR,
    item VARCHAR,
    discovered_at TIMESTAMP WITH TIME ZONE,
    program_name VARCHAR
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH recent_data AS (
        SELECT 'domain'::VARCHAR AS type, domain::VARCHAR AS item, domains.discovered_at, program_id
        FROM domains
        WHERE domains.discovered_at > CURRENT_TIMESTAMP - (days_back * INTERVAL '1 day')
        UNION ALL
        SELECT 'ip'::VARCHAR AS type, ip::VARCHAR AS item, ips.discovered_at, program_id
        FROM ips
        WHERE ips.discovered_at > CURRENT_TIMESTAMP - (days_back * INTERVAL '1 day')
        UNION ALL
        SELECT 'url'::VARCHAR AS type, url::VARCHAR AS item, urls.discovered_at, program_id
        FROM urls
        WHERE urls.discovered_at > CURRENT_TIMESTAMP - (days_back * INTERVAL '1 day')
    )
    SELECT r.type, r.item, r.discovered_at, p.name AS program_name
    FROM recent_data r
    JOIN programs p ON r.program_id = p.id
    ORDER BY r.discovered_at DESC;
END;
$$;

CREATE OR REPLACE FUNCTION get_resolved_domains_for_program(program_name VARCHAR)
RETURNS TABLE (
    domain VARCHAR,
    ips INTEGER[],
    discovered_at TIMESTAMP WITH TIME ZONE
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT d.domain, d.ips, d.discovered_at
    FROM domains d
    JOIN programs p ON d.program_id = p.id
    WHERE p.name = program_name
        AND d.ips IS NOT NULL
        AND array_length(d.ips, 1) > 0
    ORDER BY d.discovered_at DESC;
END;
$$;

-- Insert the program 'h3xit'
INSERT INTO programs (name) VALUES ('h3xit') ON CONFLICT (name) DO NOTHING;
INSERT INTO programs (name) VALUES ('desjardins') ON CONFLICT (name) DO NOTHING;
INSERT INTO programs (name) VALUES ('test') ON CONFLICT (name) DO NOTHING;

INSERT INTO program_cidrs (program_id, cidr) VALUES 
((SELECT id FROM programs WHERE name = 'desjardins'), '142.195.0.0/16');

-- Insert the scope regexes for 'h3xit
INSERT INTO program_scopes (program_id, regex) VALUES 
((SELECT id FROM programs WHERE name = 'h3xit'), '(.*\.)?h3x\.it$'),
((SELECT id FROM programs WHERE name = 'h3xit'), '(.*\.)?h3xit\.io$'),
((SELECT id FROM programs WHERE name = 'desjardins'), '.*desjardins.*'),
((SELECT id FROM programs WHERE name = 'desjardins'), '.*dsf-dfs.*'),
((SELECT id FROM programs WHERE name = 'desjardins'), '.*duproprio.*'),
((SELECT id FROM programs WHERE name = 'desjardins'), '.*disnat.*'),
((SELECT id FROM programs WHERE name = 'desjardins'), '.*bonidollar.*'),
((SELECT id FROM programs WHERE name = 'desjardins'), '.*bonusdollars.*'),
((SELECT id FROM programs WHERE name = 'desjardins'), '.*lapersonnelle.*'),
((SELECT id FROM programs WHERE name = 'desjardins'), '.*desjardinsbank.*'),
((SELECT id FROM programs WHERE name = 'desjardins'), '.*fondsdesjardins.*'),
((SELECT id FROM programs WHERE name = 'desjardins'), '.*desjardinsinsurance.*'),
((SELECT id FROM programs WHERE name = 'desjardins'), '.*desjardinsassurancevie.*'),
((SELECT id FROM programs WHERE name = 'desjardins'), '.*desjardinsgeneralinsurances.*'),
((SELECT id FROM programs WHERE name = 'desjardins'), '.*desjardinsassurancesgenerales.*'),
((SELECT id FROM programs WHERE name = 'desjardins'), '.*duproprio.*'),
((SELECT id FROM programs WHERE name = 'desjardins'), '.*hexavest.*'),
((SELECT id FROM programs WHERE name = 'desjardins'), '.*sfl.*'),
((SELECT id FROM programs WHERE name = 'desjardins'), '.*dfsi.*'),
((SELECT id FROM programs WHERE name = 'desjardins'), '.*investissementdesjardins.*'),
((SELECT id FROM programs WHERE name = 'desjardins'), '.*sflplacement.*'),
-- ((SELECT id FROM programs WHERE name = 'desjardins'), '(.*\.)?desjardins\.com$'),
-- ((SELECT id FROM programs WHERE name = 'desjardins'), '(.*\.)?dsf-dfs\.com$'),
-- ((SELECT id FROM programs WHERE name = 'desjardins'), '(.*\.)?duproprio\.com$'),
((SELECT id FROM programs WHERE name = 'test'), '(.*\.)?test\.com$'),
((SELECT id FROM programs WHERE name = 'test'), '(.*\.)?example\.com$'),
((SELECT id FROM programs WHERE name = 'test'), '(.*\.)?example\.net$');

