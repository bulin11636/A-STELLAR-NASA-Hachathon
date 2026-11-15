import schema from '../types/policies.schema.json';
import type { PolicyCatalog } from '../types/routeMetadata.ts';
import { apiRequest } from './apiClient.ts';
import { checkSchema } from './metadata.ts';
export type { PolicyCatalog };

export function decodePlanningPolicies(body: unknown): PolicyCatalog {
  if (!checkSchema(body,schema,schema)) throw new Error('Unsupported planning-policy catalog.');
  const catalog=body as PolicyCatalog;
  if (new Set(catalog.profiles.map(p=>p.profile_id)).size!==4 || new Set(catalog.resolutions.map(p=>p.profile_id)).size!==3) throw new Error('Incomplete planning-policy catalog.');
  return catalog;
}
export function getPlanningPolicies(signal?: AbortSignal): Promise<PolicyCatalog> {
  return apiRequest('/api/v1/planning/policies',decodePlanningPolicies,{signal});
}
