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