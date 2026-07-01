export type FeedbackCategory = 'bug' | 'ux' | 'account' | 'suggestion'

export type FeedbackStatus = 'submitted'

export type FeedbackSubmitter = {
  userId: string
  profileId?: number
  authSource?: string
}

export type FeedbackRecord = {
  id: string
  category: FeedbackCategory
  content: string
  contact: string
  createdAt: string
  status: FeedbackStatus
  submitter: FeedbackSubmitter
}
