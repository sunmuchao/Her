export type TabType = 'matchmaker' | 'relationships' | 'profile'

export type SubView =
  | 'main'
  | 'recommendation-inbox'
  | 'candidate-detail'
  | 'chat'
  | 'verification'
  | 'trust-center'
  | 'collected-preferences'

export type AppPage =
  | 'splash'
  | 'auth-welcome'
  | 'auth-one-click'
  | 'auth-phone'
  | 'auth-verification-code'
  | 'auth-wechat-binding'
  | 'auth-new-user-welcome'
  | 'auth-onboarding'
  | 'auth-recovery'
  | 'main-matchmaker'
  | 'main-relationships'
  | 'main-profile'
  | 'sub-recommendation-inbox'
  | 'sub-candidate-detail'
  | 'sub-chat'
  | 'sub-verification'
  | 'sub-trust-center'
  | 'sub-collected-preferences'
  | 'ops-workbench'

/** @deprecated Use AppPage */
export type DemoPage = AppPage
