'use client'

import { X, RefreshCw, Clock, AlertTriangle, CheckCircle, Loader } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getErrorMessage } from '@/lib/api/errors'
import { useOpsTaskDetail } from '@/hooks/use-ops-workbench'

type TaskDetail = {
  task_id: string
  job_id?: string
  task_type?: 'recommendation' | 'matchmaking' | 'chat'
  job_type?: string
  status: 'pending' | 'processing' | 'retry_pending' | 'succeeded' | 'failed'
  payload?: Record<string, unknown>
  created_at: string
  started_at?: string
  finished_at?: string
  finished_reason?: string
  error_message?: string
  retry_count?: number
  target?: string
}

type TaskDetailDrawerProps = {
  taskId: string | null
  pollPath?: string | null
  onClose: () => void
  onRetry?: (taskId: string) => void
}

const STATUS_CONFIG = {
  pending: {
    label: '待处理',
    color: 'text-gray-600',
    bgColor: 'bg-gray-100',
    icon: Clock,
  },
  processing: {
    label: '处理中',
    color: 'text-blue-600',
    bgColor: 'bg-blue-100',
    icon: Loader,
  },
  retry_pending: {
    label: '等待重试',
    color: 'text-amber-600',
    bgColor: 'bg-amber-100',
    icon: RefreshCw,
  },
  succeeded: {
    label: '已完成',
    color: 'text-green-600',
    bgColor: 'bg-green-100',
    icon: CheckCircle,
  },
  failed: {
    label: '失败',
    color: 'text-red-600',
    bgColor: 'bg-red-100',
    icon: AlertTriangle,
  },
}

export default function TaskDetailDrawer({ taskId, pollPath, onClose, onRetry }: TaskDetailDrawerProps) {
  const { data, isLoading, error } = useOpsTaskDetail(pollPath || null, Boolean(taskId))
  const task = (data?.job || null) as TaskDetail | null
  const resolvedTaskId = task?.job_id || task?.task_id || taskId

  if (!taskId) return null

  const statusConfig = task ? STATUS_CONFIG[task.status] : null

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center">
      {/* 背景遮罩 */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* 抽屉面板 */}
      <div
        className={cn(
          'relative w-full max-w-2xl bg-background rounded-t-2xl shadow-2xl',
          'transform transition-transform duration-300 ease-out',
          'max-h-[85vh] overflow-hidden flex flex-col'
        )}
      >
        {/* 头部 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div>
            <h2 className="text-lg font-semibold">任务详情</h2>
            <p className="text-sm text-muted-foreground">{taskId}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-2 hover:bg-muted transition-colors"
            aria-label="关闭"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
          {isLoading && (
            <div className="flex items-center justify-center py-12">
              <Loader className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          )}

          {error && (
            <div className="rounded-lg bg-red-50 p-4 text-red-700">
              <p className="font-medium">加载失败</p>
              <p className="text-sm mt-1">{getErrorMessage(error)}</p>
            </div>
          )}

          {task && !isLoading && !error && (
            <>
              {/* 状态信息 */}
              <div className="flex items-center gap-3">
                {statusConfig && (
                  <div
                    className={cn(
                      'flex items-center gap-2 px-4 py-2 rounded-full',
                      statusConfig.bgColor
                    )}
                  >
                    <statusConfig.icon className={cn('h-4 w-4', statusConfig.color)} />
                    <span className={cn('font-medium', statusConfig.color)}>
                      {statusConfig.label}
                    </span>
                  </div>
                )}
                <p className="text-sm text-muted-foreground">
                  重试次数: {task.retry_count ?? 0}
                </p>
              </div>

              {/* 基本信息 */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-muted-foreground">任务类型</p>
                  <p className="text-sm font-medium capitalize">{task.job_type || task.task_type || task.target || 'unknown'}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">当前状态</p>
                  <p className="text-sm font-medium">
                    {task.status}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">创建时间</p>
                  <p className="text-sm font-medium">
                    {new Date(task.created_at).toLocaleString('zh-CN')}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">完成时间</p>
                  <p className="text-sm font-medium">
                    {task.finished_at
                      ? new Date(task.finished_at).toLocaleString('zh-CN')
                      : '—'}
                  </p>
                </div>
              </div>

              {/* 任务参数 */}
              <div>
                <p className="text-xs text-muted-foreground mb-2">任务载荷</p>
                <pre className="rounded-lg bg-muted p-3 text-xs overflow-auto max-h-48">
                  {JSON.stringify(task.payload || {}, null, 2)}
                </pre>
              </div>

              {/* 错误信息 */}
              {task.status === 'failed' && task.error_message && (
                <div className="rounded-lg bg-red-50 p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <AlertTriangle className="h-4 w-4 text-red-600" />
                    <p className="font-medium text-red-700">错误信息</p>
                  </div>
                  <p className="text-sm text-red-700">{task.error_message}</p>
                </div>
              )}
            </>
          )}
        </div>

        {/* 底部操作按钮 */}
        {task && !isLoading && !error && (
          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-border bg-muted/30">
            {task.status === 'failed' && onRetry && resolvedTaskId && (
              <button
                type="button"
                onClick={() => onRetry(resolvedTaskId)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                <RefreshCw className="h-4 w-4" />
                重试任务
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg border border-border hover:bg-muted transition-colors"
            >
              关闭
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
