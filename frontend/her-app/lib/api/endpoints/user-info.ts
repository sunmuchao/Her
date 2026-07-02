import { gatewayJson } from '@/lib/api/client'

export type UserInfo = {
  user_id?: string
  profile_id?: number
  user_name?: string
  avatar_url?: string
  nickname?: string
}

/**
 * 获取用户基本信息（管理员使用）
 */
export async function fetchUserInfo(profileId: number): Promise<UserInfo> {
  const response = await gatewayJson<{ profile?: UserInfo }>(
    `/v1/profiles/${profileId}/basic-info`,
    { includeAuth: true },
  )

  return response.profile || {
    profile_id: profileId,
    user_name: `用户 #${profileId}`,
  }
}