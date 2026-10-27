-- Sample control-plane rows for the Demo Factory portal.
-- Re-running replaces these rows. Tenant clinical data is not stored here.

SET XACT_ABORT ON;
BEGIN TRANSACTION;

DECLARE @Molina uniqueidentifier = '11111111-1111-4111-8111-111111111111';
DECLARE @Humana uniqueidentifier = '22222222-2222-4222-8222-222222222222';
DECLARE @Uhc    uniqueidentifier = '33333333-3333-4333-8333-333333333333';
DECLARE @User   uniqueidentifier = '44444444-4444-4444-8444-444444444444';
DECLARE @TplClaimStatus uniqueidentifier = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1';
DECLARE @TplClaimsAuth  uniqueidentifier = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2';
DECLARE @TplCopilot     uniqueidentifier = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3';
DECLARE @EnvMolina uniqueidentifier = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1';
DECLARE @EnvHumana uniqueidentifier = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2';
DECLARE @EnvUhc    uniqueidentifier = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb3';

DELETE FROM dbo.UsageCost WHERE EnvironmentId IN (@EnvMolina, @EnvHumana, @EnvUhc);
DELETE FROM dbo.ConversationLog WHERE EnvironmentId IN (@EnvMolina, @EnvHumana, @EnvUhc);
DELETE FROM dbo.DeploymentLog WHERE EnvironmentId IN (@EnvMolina, @EnvHumana, @EnvUhc);
DELETE FROM dbo.Environment WHERE EnvironmentId IN (@EnvMolina, @EnvHumana, @EnvUhc);
DELETE FROM dbo.UserAccess WHERE UserId = @User;
DELETE FROM dbo.BrandingConfig WHERE CustomerId IN (@Molina, @Humana, @Uhc);
DELETE FROM dbo.Template WHERE TemplateId IN (@TplClaimStatus, @TplClaimsAuth, @TplCopilot);
DELETE FROM dbo.Customer WHERE CustomerId IN (@Molina, @Humana, @Uhc);
DELETE FROM dbo.AppUser WHERE UserId = @User;

INSERT INTO dbo.AppUser (UserId, EntraObjectId, Email, DisplayName, Role) VALUES
(@User, NULL, N'jordan.lee@example.invalid', N'Jordan Lee', N'SalesEngineer');

INSERT INTO dbo.Customer (CustomerId, Name, TenantId, Status, CreatedAt) VALUES
(@Molina, N'Molina Healthcare', N'molina-001', N'Active', '2026-10-01T15:00:00'),
(@Humana, N'Humana',            N'humana-001', N'Active', '2026-10-08T15:00:00'),
(@Uhc,    N'UnitedHealthcare',  N'uhc-001',    N'Active', '2026-10-20T15:00:00');

INSERT INTO dbo.BrandingConfig (BrandingConfigId, CustomerId, PortalName, LogoUrl, PrimaryColor, SecondaryColor) VALUES
('11111111-1111-4111-8111-111111111201', @Molina, N'Molina Provider Services', NULL, N'#0057B8', N'#00A3E0'),
('22222222-2222-4222-8222-222222222201', @Humana, N'Humana Provider Services', NULL, N'#4B9B2A', N'#78BE20'),
('33333333-3333-4333-8333-333333333201', @Uhc,    N'UnitedHealthcare Provider Services', NULL, N'#002677', N'#00A9E0');

INSERT INTO dbo.UserAccess (UserAccessId, UserId, CustomerId) VALUES
('44444444-4444-4444-8444-444444444401', @User, @Molina),
('44444444-4444-4444-8444-444444444402', @User, @Humana),
('44444444-4444-4444-8444-444444444403', @User, @Uhc);

INSERT INTO dbo.Template (TemplateId, Name, Status, DefinitionJson, CreatedByUserId, CreatedAt) VALUES
(@TplClaimStatus, N'Claim Status Agent', N'Saved',
 N'{"channels":["chat","voice"],"capabilities":["claim-status","denial-explanation","payment-details"],"syntheticMembers":250,"estimatedMinutes":2}',
 @User, '2026-09-15T18:00:00'),
(@TplClaimsAuth, N'Claims + Authorization', N'Saved',
 N'{"channels":["chat"],"capabilities":["claim-status","authorization"],"syntheticMembers":500,"estimatedMinutes":3}',
 @User, '2026-09-22T18:00:00'),
(@TplCopilot, N'Provider Service Copilot', N'Saved',
 N'{"channels":["chat","voice"],"capabilities":["claim-status","denial-explanation","payment-details","authorization"],"syntheticMembers":1000,"estimatedMinutes":4}',
 @User, '2026-10-02T18:00:00');

INSERT INTO dbo.Environment (EnvironmentId, CustomerId, TemplateId, Name, Status, ExpiresAt, CreatedAt) VALUES
(@EnvMolina, @Molina, @TplCopilot,    N'Molina Demo', N'Active',    '2026-11-26T00:00:00', '2026-10-12T16:00:00'),
(@EnvHumana, @Humana, @TplClaimsAuth, N'Humana Demo', N'Active',    '2026-11-26T00:00:00', '2026-10-18T16:00:00'),
(@EnvUhc,    @Uhc,    @TplClaimStatus, N'UHC Demo',   N'Deploying', '2026-11-26T00:00:00', '2026-10-26T21:00:00');

INSERT INTO dbo.DeploymentLog (DeploymentLogId, EnvironmentId, Action, Status, Message, StartedAt, FinishedAt) VALUES
('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbb11', @EnvMolina, N'Deploy', N'Succeeded', N'Environment registered. Tenant resource group is created later from the portal.', '2026-10-12T16:00:00', '2026-10-12T16:01:20'),
('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbb21', @EnvHumana, N'Deploy', N'Succeeded', N'Environment registered. Tenant resource group is created later from the portal.', '2026-10-18T16:00:00', '2026-10-18T16:01:05'),
('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbb31', @EnvUhc,    N'Deploy', N'Running',   N'Waiting to create the tenant resource group.', '2026-10-26T21:04:00', NULL);

INSERT INTO dbo.ConversationLog (ConversationLogId, EnvironmentId, Channel, Transcript, CreatedAt) VALUES
('cccccccc-cccc-4ccc-8ccc-ccccccccccc1', @EnvMolina, N'chat',
 N'User: Check claim status for CLM-MOL-1002. Assistant: Claim CLM-MOL-1002 is Denied. Service is not covered under the member plan for this benefit year.',
 '2026-10-24T18:12:00'),
('cccccccc-cccc-4ccc-8ccc-ccccccccccc2', @EnvMolina, N'voice',
 N'User: Find the payment for Maria Alvarez. Assistant: Payment PAY-MOL-1001 for 142.50 was issued on 12 October 2026 by EFT.',
 '2026-10-25T15:40:00'),
('cccccccc-cccc-4ccc-8ccc-ccccccccccc3', @EnvHumana, N'chat',
 N'User: Why was CLM-HUM-2002 denied? Assistant: Prior authorization was required and was not on file at the time of service.',
 '2026-10-25T19:05:00');

INSERT INTO dbo.UsageCost (UsageCostId, EnvironmentId, Meter, Quantity, Cost, RecordedAt) VALUES
('dddddddd-dddd-4ddd-8ddd-ddddddddddd1', @EnvMolina, N'chat-turns', 128, 14.20, '2026-10-26T00:00:00'),
('dddddddd-dddd-4ddd-8ddd-ddddddddddd2', @EnvMolina, N'voice-minutes', 36, 8.10, '2026-10-26T00:00:00'),
('dddddddd-dddd-4ddd-8ddd-ddddddddddd3', @EnvHumana, N'chat-turns', 86, 9.40, '2026-10-26T00:00:00');

COMMIT TRANSACTION;
