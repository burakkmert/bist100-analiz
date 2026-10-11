// GET/PUT /me/profile — risk profili ve bütçe.
import type { RiskProfile } from '@/store/settings';
import { api, USE_MOCK } from './client';

export interface Profile {
  risk_profile: RiskProfile;
  budget: number | null;
}

export async function putProfile(profile: Profile): Promise<Profile> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 400)); // gerçekçi gecikme
    return profile;
  }
  return api<Profile>('/me/profile', { method: 'PUT', body: JSON.stringify(profile) });
}
