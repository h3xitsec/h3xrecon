-- Insert the program 'h3xit'
INSERT INTO programs (name) VALUES ('test') ON CONFLICT (name) DO NOTHING;

-- Insert the scope regexes for 'h3xit
INSERT INTO program_scopes (program_id, regex) VALUES 
((SELECT id FROM programs WHERE name = 'test'), '(.*\.)?test\.com$'),
((SELECT id FROM programs WHERE name = 'test'), '(.*\.)?example\.com$'),
((SELECT id FROM programs WHERE name = 'test'), '(.*\.)?example\.net$');