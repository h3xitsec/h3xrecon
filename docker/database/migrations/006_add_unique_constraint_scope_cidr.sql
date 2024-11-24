-- Remove duplicate scopes keeping only the one with lowest ID
WITH duplicate_scopes AS (
    SELECT program_id, regex, MIN(id) as keep_id
    FROM program_scopes
    GROUP BY program_id, regex
    HAVING COUNT(*) > 1
)
DELETE FROM program_scopes
WHERE id IN (
    SELECT ps.id 
    FROM program_scopes ps
    JOIN duplicate_scopes ds ON ps.program_id = ds.program_id AND ps.regex = ds.regex
    WHERE ps.id > ds.keep_id
);

-- Remove duplicate CIDRs keeping only the one with lowest ID
WITH duplicate_cidrs AS (
    SELECT program_id, cidr, MIN(id) as keep_id
    FROM program_cidrs
    GROUP BY program_id, cidr
    HAVING COUNT(*) > 1
)
DELETE FROM program_cidrs
WHERE id IN (
    SELECT pc.id 
    FROM program_cidrs pc
    JOIN duplicate_cidrs dc ON pc.program_id = dc.program_id AND pc.cidr = dc.cidr
    WHERE pc.id > dc.keep_id
);

-- Add unique constraint to prevent duplicate scopes for the same program
ALTER TABLE program_scopes
ADD CONSTRAINT unique_program_scope UNIQUE (program_id, regex);

-- Add unique constraint to prevent duplicate CIDRs for the same program
ALTER TABLE program_cidrs
ADD CONSTRAINT unique_program_cidr UNIQUE (program_id, cidr);