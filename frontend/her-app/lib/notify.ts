import { toast } from 'sonner'
import { getErrorMessage } from '@/lib/api/errors'

export function notifyError(error: unknown, fallback?: string) {
  toast.error(getErrorMessage(error, fallback))
}

export function notifySuccess(message: string) {
  toast.success(message)
}
