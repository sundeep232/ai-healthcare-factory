-- Control-plane catalog for sqldb-controlplane.
-- Customers, templates, environments, access, and logs only.
-- Each tenant's own resources and data are created later, in that tenant's resource group.
-- Safe to run more than once.

DROP TABLE IF EXISTS dbo.Payment;
DROP TABLE IF EXISTS dbo.[Authorization];
DROP TABLE IF EXISTS dbo.Claim;
DROP TABLE IF EXISTS dbo.Member;
DROP TABLE IF EXISTS dbo.Provider;

IF OBJECT_ID(N'dbo.Customer', N'U') IS NULL
CREATE TABLE dbo.Customer (
    CustomerId uniqueidentifier NOT NULL CONSTRAINT PK_Customer PRIMARY KEY,
    Name       nvarchar(200)    NOT NULL,
    TenantId   nvarchar(64)     NOT NULL CONSTRAINT UQ_Customer_TenantId UNIQUE,
    Status     nvarchar(32)     NOT NULL,
    CreatedAt  datetime2(0)     NOT NULL
);

IF OBJECT_ID(N'dbo.BrandingConfig', N'U') IS NULL
CREATE TABLE dbo.BrandingConfig (
    BrandingConfigId uniqueidentifier NOT NULL CONSTRAINT PK_BrandingConfig PRIMARY KEY,
    CustomerId       uniqueidentifier NOT NULL CONSTRAINT FK_BrandingConfig_Customer REFERENCES dbo.Customer (CustomerId),
    PortalName       nvarchar(200)    NOT NULL,
    LogoUrl          nvarchar(500)    NULL,
    PrimaryColor     nvarchar(16)     NOT NULL,
    SecondaryColor   nvarchar(16)     NULL
);

IF OBJECT_ID(N'dbo.AppUser', N'U') IS NULL
CREATE TABLE dbo.AppUser (
    UserId         uniqueidentifier NOT NULL CONSTRAINT PK_AppUser PRIMARY KEY,
    EntraObjectId  uniqueidentifier NULL,
    Email          nvarchar(320)    NOT NULL,
    DisplayName    nvarchar(200)    NOT NULL,
    Role           nvarchar(64)     NOT NULL
);

IF OBJECT_ID(N'dbo.UserAccess', N'U') IS NULL
CREATE TABLE dbo.UserAccess (
    UserAccessId uniqueidentifier NOT NULL CONSTRAINT PK_UserAccess PRIMARY KEY,
    UserId       uniqueidentifier NOT NULL CONSTRAINT FK_UserAccess_AppUser REFERENCES dbo.AppUser (UserId),
    CustomerId   uniqueidentifier NOT NULL CONSTRAINT FK_UserAccess_Customer REFERENCES dbo.Customer (CustomerId),
    CONSTRAINT UQ_UserAccess_User_Customer UNIQUE (UserId, CustomerId)
);

IF OBJECT_ID(N'dbo.Template', N'U') IS NULL
CREATE TABLE dbo.Template (
    TemplateId      uniqueidentifier NOT NULL CONSTRAINT PK_Template PRIMARY KEY,
    Name            nvarchar(200)    NOT NULL,
    Status          nvarchar(32)     NOT NULL,
    DefinitionJson  nvarchar(max)    NOT NULL,
    CreatedByUserId uniqueidentifier NULL CONSTRAINT FK_Template_AppUser REFERENCES dbo.AppUser (UserId),
    CreatedAt       datetime2(0)     NOT NULL
);

IF OBJECT_ID(N'dbo.Environment', N'U') IS NULL
CREATE TABLE dbo.Environment (
    EnvironmentId uniqueidentifier NOT NULL CONSTRAINT PK_Environment PRIMARY KEY,
    CustomerId    uniqueidentifier NOT NULL CONSTRAINT FK_Environment_Customer REFERENCES dbo.Customer (CustomerId),
    TemplateId    uniqueidentifier NULL CONSTRAINT FK_Environment_Template REFERENCES dbo.Template (TemplateId),
    Name          nvarchar(200)    NOT NULL,
    Status        nvarchar(32)     NOT NULL,
    ExpiresAt     datetime2(0)     NULL,
    CreatedAt     datetime2(0)     NOT NULL
);

IF OBJECT_ID(N'dbo.DeploymentLog', N'U') IS NULL
CREATE TABLE dbo.DeploymentLog (
    DeploymentLogId uniqueidentifier NOT NULL CONSTRAINT PK_DeploymentLog PRIMARY KEY,
    EnvironmentId   uniqueidentifier NOT NULL CONSTRAINT FK_DeploymentLog_Environment REFERENCES dbo.Environment (EnvironmentId),
    Action          nvarchar(32)     NOT NULL,
    Status          nvarchar(32)     NOT NULL,
    Message         nvarchar(1000)   NULL,
    StartedAt       datetime2(0)     NOT NULL,
    FinishedAt      datetime2(0)     NULL
);

IF OBJECT_ID(N'dbo.ConversationLog', N'U') IS NULL
CREATE TABLE dbo.ConversationLog (
    ConversationLogId uniqueidentifier NOT NULL CONSTRAINT PK_ConversationLog PRIMARY KEY,
    EnvironmentId     uniqueidentifier NOT NULL CONSTRAINT FK_ConversationLog_Environment REFERENCES dbo.Environment (EnvironmentId),
    Channel           nvarchar(16)     NOT NULL,
    Transcript        nvarchar(max)    NOT NULL,
    CreatedAt         datetime2(0)     NOT NULL
);

IF OBJECT_ID(N'dbo.UsageCost', N'U') IS NULL
CREATE TABLE dbo.UsageCost (
    UsageCostId   uniqueidentifier NOT NULL CONSTRAINT PK_UsageCost PRIMARY KEY,
    EnvironmentId uniqueidentifier NOT NULL CONSTRAINT FK_UsageCost_Environment REFERENCES dbo.Environment (EnvironmentId),
    Meter         nvarchar(64)     NOT NULL,
    Quantity      decimal(18, 4)   NOT NULL,
    Cost          decimal(18, 4)   NOT NULL,
    RecordedAt    datetime2(0)     NOT NULL
);
