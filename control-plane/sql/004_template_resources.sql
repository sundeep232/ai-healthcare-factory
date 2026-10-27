-- Record which tenant modules each template creates.
UPDATE dbo.Template
SET DefinitionJson = JSON_MODIFY(DefinitionJson, '$.resources', JSON_QUERY(N'["sql","portal","openai","speech","communication"]'))
WHERE Name = N'Claim Status Agent';

UPDATE dbo.Template
SET DefinitionJson = JSON_MODIFY(DefinitionJson, '$.resources', JSON_QUERY(N'["sql","portal","openai"]'))
WHERE Name = N'Claims + Authorization';

UPDATE dbo.Template
SET DefinitionJson = JSON_MODIFY(DefinitionJson, '$.resources', JSON_QUERY(N'["sql","portal","openai","speech","communication"]'))
WHERE Name = N'Provider Service Copilot';
