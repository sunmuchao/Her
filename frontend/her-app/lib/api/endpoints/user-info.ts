import { gatewayJson } from '@/lib/api/client'

export type UserInfo = {
  user_id?: string
  profile_id?: number
  user_name?: string
  avatar_url?: string
  nickname?: string
  education?: string
}

/**
 * 获取用户基本信息（管理员使用）
 */
export async function fetchUserInfo(
  profileId: number,
  signal?: AbortSignal,
  options?: { sourceDsn?: string; sourceTableName?: string },
): Promise<UserInfo> {
  const query = new URLSearchParams()
  if (options?.sourceDsn) query.set('source_dsn', options.sourceDsn)
  if (options?.sourceTableName) query.set('source_table_name', options.sourceTableName)

  const response = await gatewayJson<{ profile?: UserInfo }>(
    `/v1/profiles/${profileId}/basic-info${query.toString() ? `?${query.toString()}` : ''}`,
    {
      includeAuth: true,
      signal, // 支持请求取消
    },
  )

  return response.profile || {
    profile_id: profileId,
    user_name: `用户 #${profileId}`,
  }
}
