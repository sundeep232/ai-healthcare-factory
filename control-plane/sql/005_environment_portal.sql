-- Remembers the provider portal address printed at the end of a tenant deploy.

IF COL_LENGTH(N'dbo.Environment', N'PortalUrl') IS NULL
    ALTER TABLE dbo.Environment ADD PortalUrl nvarchar(300) NULL;
