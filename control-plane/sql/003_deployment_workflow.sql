-- Lets the control plane remember which GitHub Actions run is deploying a demo
-- and store the log the portal shows.

IF COL_LENGTH(N'dbo.Environment', N'Slug') IS NULL
    ALTER TABLE dbo.Environment ADD Slug nvarchar(63) NULL;

IF COL_LENGTH(N'dbo.DeploymentLog', N'WorkflowRunId') IS NULL
    ALTER TABLE dbo.DeploymentLog ADD WorkflowRunId bigint NULL;

IF COL_LENGTH(N'dbo.DeploymentLog', N'LogText') IS NULL
    ALTER TABLE dbo.DeploymentLog ADD LogText nvarchar(max) NULL;
