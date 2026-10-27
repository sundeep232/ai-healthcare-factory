export type Customer = {
  id: string;
  name: string;
  tenantId: string;
  status: string;
  createdAt: string;
  portalName: string | null;
  primaryColor: string | null;
  secondaryColor: string | null;
};

export type Template = {
  id: string;
  name: string;
  status: string;
  definition: {
    channels?: string[];
    capabilities?: string[];
    syntheticMembers?: number;
    estimatedMinutes?: number;
  };
  createdAt: string;
  createdBy: string | null;
};

export type EnvironmentSummary = {
  id: string;
  name: string;
  status: string;
  expiresAt: string | null;
  createdAt: string;
  customerId: string;
  customerName: string;
  tenantId: string;
  portalName: string | null;
  primaryColor: string | null;
  templateId: string | null;
  templateName: string | null;
};

export type EnvironmentDetail = EnvironmentSummary & {
  secondaryColor: string | null;
  deployments: {
    id: string;
    action: string;
    status: string;
    message: string | null;
    startedAt: string;
    finishedAt: string | null;
  }[];
  conversations: {
    id: string;
    channel: string;
    transcript: string;
    createdAt: string;
  }[];
  usage: {
    id: string;
    meter: string;
    quantity: number;
    cost: number;
    recordedAt: string;
  }[];
};
