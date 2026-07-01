export type FeedbackCategory = 'bug' | 'ux' | 'account' | 'suggestion'

export type FeedbackRecord = {
  id: string
  category: FeedbackCategory
  content: string
  contact: string
  createdAt: string
}
