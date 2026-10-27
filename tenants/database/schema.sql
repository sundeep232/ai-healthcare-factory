-- Payer tables for one tenant database. Terraform creates sqldb-tenant; this script creates the tables.
IF OBJECT_ID(N'dbo.[PLAN]', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.[PLAN] (
        plan_id     nvarchar(32)  NOT NULL PRIMARY KEY,
        plan_name   nvarchar(100) NOT NULL,
        plan_type   nvarchar(50)  NOT NULL,
        created_at  datetime2     NOT NULL
    );
END
GO
IF OBJECT_ID(N'dbo.DIAGNOSIS_CODE', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.DIAGNOSIS_CODE (
        diagnosis_code nvarchar(20)  NOT NULL PRIMARY KEY,
        description    nvarchar(200) NOT NULL,
        code_type      nvarchar(20)  NOT NULL
    );
END
GO
IF OBJECT_ID(N'dbo.PROCEDURE_CODE', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PROCEDURE_CODE (
        procedure_code nvarchar(20)  NOT NULL PRIMARY KEY,
        description    nvarchar(200) NOT NULL,
        code_type      nvarchar(20)  NOT NULL
    );
END
GO
IF OBJECT_ID(N'dbo.PROVIDER_SPECIALTY', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PROVIDER_SPECIALTY (
        specialty_id   nvarchar(32)  NOT NULL PRIMARY KEY,
        specialty_name nvarchar(100) NOT NULL
    );
END
GO
IF OBJECT_ID(N'dbo.CARE_PROGRAM', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CARE_PROGRAM (
        program_id   nvarchar(32) NOT NULL PRIMARY KEY,
        program_type nvarchar(80) NOT NULL UNIQUE
    );
END
GO
IF OBJECT_ID(N'dbo.[MEMBER]', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.[MEMBER] (
        member_id       nvarchar(32)  NOT NULL PRIMARY KEY,
        member_number   nvarchar(32)  NOT NULL,
        first_name      nvarchar(80)  NOT NULL,
        last_name       nvarchar(80)  NOT NULL,
        date_of_birth   date          NOT NULL,
        gender          nvarchar(10)  NOT NULL,
        address_line1   nvarchar(120) NOT NULL,
        address_line2   nvarchar(120) NULL,
        city            nvarchar(80)  NOT NULL,
        state           nvarchar(2)   NOT NULL,
        zip_code        nvarchar(10)  NOT NULL,
        phone_number    nvarchar(20)  NOT NULL,
        email           nvarchar(200) NOT NULL,
        plan_id         nvarchar(32)  NOT NULL,
        effective_date  date          NOT NULL,
        termination_date date         NULL,
        created_at      datetime2     NOT NULL,
        CONSTRAINT FK_MEMBER_PLAN FOREIGN KEY (plan_id) REFERENCES dbo.[PLAN] (plan_id)
    );
END
GO
IF OBJECT_ID(N'dbo.PROVIDER', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PROVIDER (
        provider_id    nvarchar(32)  NOT NULL PRIMARY KEY,
        npi_number     nvarchar(10)  NOT NULL,
        provider_name  nvarchar(160) NOT NULL,
        provider_type  nvarchar(40)  NOT NULL,
        specialty      nvarchar(100) NOT NULL,
        phone_number   nvarchar(20)  NOT NULL,
        address_line1  nvarchar(120) NOT NULL,
        address_line2  nvarchar(120) NULL,
        city           nvarchar(80)  NOT NULL,
        state          nvarchar(2)   NOT NULL,
        zip_code       nvarchar(10)  NOT NULL,
        taxonomy_code  nvarchar(20)  NOT NULL,
        created_at     datetime2     NOT NULL
    );
END
GO
IF OBJECT_ID(N'dbo.[AUTHORIZATION]', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.[AUTHORIZATION] (
        authorization_id     nvarchar(32)  NOT NULL PRIMARY KEY,
        member_id            nvarchar(32)  NOT NULL,
        provider_id          nvarchar(32)  NOT NULL,
        authorization_number nvarchar(32)  NOT NULL,
        service_type         nvarchar(80)  NOT NULL,
        status               nvarchar(20)  NOT NULL,
        request_date         date          NOT NULL,
        approval_date        date          NULL,
        start_date           date          NOT NULL,
        end_date             date          NOT NULL,
        diagnosis_code       nvarchar(20)  NOT NULL,
        procedure_code       nvarchar(20)  NOT NULL,
        authorized_units     int           NOT NULL,
        created_at           datetime2     NOT NULL,
        CONSTRAINT FK_AUTHORIZATION_MEMBER FOREIGN KEY (member_id) REFERENCES dbo.[MEMBER] (member_id),
        CONSTRAINT FK_AUTHORIZATION_PROVIDER FOREIGN KEY (provider_id) REFERENCES dbo.PROVIDER (provider_id),
        CONSTRAINT FK_AUTHORIZATION_DIAGNOSIS FOREIGN KEY (diagnosis_code) REFERENCES dbo.DIAGNOSIS_CODE (diagnosis_code),
        CONSTRAINT FK_AUTHORIZATION_PROCEDURE FOREIGN KEY (procedure_code) REFERENCES dbo.PROCEDURE_CODE (procedure_code)
    );
END
GO
IF OBJECT_ID(N'dbo.CLAIMS', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CLAIMS (
        claim_id         nvarchar(32)   NOT NULL PRIMARY KEY,
        member_id        nvarchar(32)   NOT NULL,
        provider_id      nvarchar(32)   NOT NULL,
        authorization_id nvarchar(32)   NULL,
        claim_number     nvarchar(32)   NOT NULL,
        service_date     date           NOT NULL,
        billed_amount    decimal(12, 2) NOT NULL,
        allowed_amount   decimal(12, 2) NOT NULL,
        paid_amount      decimal(12, 2) NOT NULL,
        claim_status     nvarchar(20)   NOT NULL,
        diagnosis_code   nvarchar(20)   NOT NULL,
        procedure_code   nvarchar(20)   NOT NULL,
        place_of_service nvarchar(40)   NOT NULL,
        created_at       datetime2      NOT NULL,
        CONSTRAINT FK_CLAIMS_MEMBER FOREIGN KEY (member_id) REFERENCES dbo.[MEMBER] (member_id),
        CONSTRAINT FK_CLAIMS_PROVIDER FOREIGN KEY (provider_id) REFERENCES dbo.PROVIDER (provider_id),
        CONSTRAINT FK_CLAIMS_AUTHORIZATION FOREIGN KEY (authorization_id) REFERENCES dbo.[AUTHORIZATION] (authorization_id),
        CONSTRAINT FK_CLAIMS_DIAGNOSIS FOREIGN KEY (diagnosis_code) REFERENCES dbo.DIAGNOSIS_CODE (diagnosis_code),
        CONSTRAINT FK_CLAIMS_PROCEDURE FOREIGN KEY (procedure_code) REFERENCES dbo.PROCEDURE_CODE (procedure_code)
    );
    CREATE INDEX IX_CLAIMS_member_id ON dbo.CLAIMS (member_id);
    CREATE INDEX IX_CLAIMS_provider_id ON dbo.CLAIMS (provider_id);
END
GO
IF OBJECT_ID(N'dbo.CARE_MANAGEMENT', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CARE_MANAGEMENT (
        care_management_id nvarchar(32)  NOT NULL PRIMARY KEY,
        member_id          nvarchar(32)  NOT NULL,
        provider_id        nvarchar(32)  NOT NULL,
        claim_id           nvarchar(32)  NOT NULL,
        program_type       nvarchar(80)  NOT NULL,
        care_manager_id    nvarchar(32)  NOT NULL,
        enrollment_date    date          NOT NULL,
        status             nvarchar(20)  NOT NULL,
        risk_level         nvarchar(20)  NOT NULL,
        notes              nvarchar(500) NULL,
        next_followup_date date          NULL,
        outcome            nvarchar(40)  NULL,
        created_at         datetime2     NOT NULL,
        CONSTRAINT FK_CARE_MEMBER FOREIGN KEY (member_id) REFERENCES dbo.[MEMBER] (member_id),
        CONSTRAINT FK_CARE_PROVIDER FOREIGN KEY (provider_id) REFERENCES dbo.PROVIDER (provider_id),
        CONSTRAINT FK_CARE_CLAIM FOREIGN KEY (claim_id) REFERENCES dbo.CLAIMS (claim_id),
        CONSTRAINT FK_CARE_PROGRAM FOREIGN KEY (program_type) REFERENCES dbo.CARE_PROGRAM (program_type)
    );
END
GO
