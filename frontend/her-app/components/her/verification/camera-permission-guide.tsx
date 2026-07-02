'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

/**
 * 摄像头权限引导组件
 *
 * 当用户拒绝摄像头权限时，显示引导步骤帮助用户重新开启权限
 */

interface CameraPermissionGuideProps {
  isOpen: boolean
  onClose: () => void
  onRetry: () => void
}

export function CameraPermissionGuide({ isOpen, onClose, onRetry }: CameraPermissionGuideProps) {
  const [currentStep, setCurrentStep] = useState(0)

  const steps = [
    {
      title: '步骤 1：找到摄像头图标',
      description: '在浏览器地址栏左侧找到摄像头图标',
      image: '/images/camera-permission-step1.png', // 需要准备引导图片
    },
    {
      title: '步骤 2：点击摄像头图标',
      description: '点击摄像头图标，会弹出权限设置菜单',
      image: '/images/camera-permission-step2.png',
    },
    {
      title: '步骤 3：选择"允许访问"',
      description: '在权限菜单中选择"允许访问摄像头和麦克风"',
      image: '/images/camera-permission-step3.png',
    },
    {
      title: '步骤 4：刷新页面',
      description: '权限设置完成后，刷新页面重新开始认证',
      image: '/images/camera-permission-step4.png',
    },
  ]

  const handleNext = () => {
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1)
    }
  }

  const handlePrevious = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="text-lg font-semibold text-red-600">
            需要摄像头和麦克风权限
          </DialogTitle>
          <DialogDescription className="text-sm text-gray-600">
            完成视频认证需要访问您的摄像头和麦克风，请按照以下步骤开启权限
          </DialogDescription>
        </DialogHeader>

        <div className="mt-4 space-y-4">
          {/* 当前步骤 */}
          <div className="bg-blue-50 rounded-lg p-4">
            <div className="flex items-center space-x-2 mb-2">
              <span className="bg-blue-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-sm font-semibold">
                {currentStep + 1}
              </span>
              <h3 className="font-semibold text-blue-900">{steps[currentStep].title}</h3>
            </div>
            <p className="text-sm text-blue-700 ml-8">{steps[currentStep].description}</p>

            {/* 引导图片（如果有） */}
            {steps[currentStep].image && (
              <div className="mt-3 ml-8">
                <img
                  src={steps[currentStep].image}
                  alt={steps[currentStep].title}
                  className="rounded border border-blue-200 max-w-full"
                />
              </div>
            )}
          </div>

          {/* 步骤进度指示器 */}
          <div className="flex items-center justify-center space-x-2">
            {steps.map((_, index) => (
              <div
                key={index}
                className={`w-2 h-2 rounded-full ${
                  index === currentStep ? 'bg-blue-500' : 'bg-gray-300'
                }`}
              />
            ))}
          </div>

          {/* 导航按钮 */}
          <div className="flex items-center justify-between space-x-2">
            <Button
              variant="outline"
              onClick={handlePrevious}
              disabled={currentStep === 0}
              className="w-1/3"
            >
              上一步
            </Button>

            {currentStep < steps.length - 1 ? (
              <Button onClick={handleNext} className="w-1/3">
                下一步
              </Button>
            ) : (
              <Button onClick={onRetry} className="w-1/3 bg-green-500 hover:bg-green-600">
                刷新页面
              </Button>
            )}
          </div>

          {/* 提示信息 */}
          <div className="bg-yellow-50 rounded p-3 text-sm text-yellow-800">
            <p className="font-semibold mb-1">温馨提示：</p>
            <ul className="list-disc list-inside space-y-1">
              <li>如果您无法找到摄像头图标，请检查浏览器设置</li>
              <li>某些浏览器可能需要在设置中手动开启权限</li>
              <li>完成后请刷新页面，系统会重新请求权限</li>
            </ul>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

/**
 * 摄像头权限请求Hook
 *
 * 尝试获取摄像头权限，如果被拒绝则显示引导UI
 */
export function useCameraPermission() {
  const [showGuide, setShowGuide] = useState(false)
  const [permissionStatus, setPermissionStatus] = useState<'granted' | 'denied' | 'prompt' | 'unknown'>('unknown')

  /**
   * 请求摄像头权限
   */
  const requestCameraPermission = async (): Promise<MediaStream | null> => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user' },
        audio: true,
      })

      setPermissionStatus('granted')
      setShowGuide(false)
      return stream
    } catch (error: any) {
      console.error('摄像头权限请求失败', error)

      if (error.name === 'NotAllowedError') {
        setPermissionStatus('denied')
        setShowGuide(true)
        return null
      }

      // 其他错误（如设备不支持）
      throw error
    }
  }

  /**
   * 检查权限状态
   */
  const checkPermissionStatus = async () => {
    try {
      // 使用Permissions API查询权限状态（部分浏览器支持）
      if ('permissions' in navigator) {
        const result = await navigator.permissions.query({ name: 'camera' as PermissionName })
        setPermissionStatus(result.state as any)
        return result.state
      }
    } catch (error) {
      console.log('Permissions API不支持', error)
    }

    return 'unknown'
  }

  /**
   * 关闭引导UI并重新尝试
   */
  const handleRetry = () => {
    setShowGuide(false)
    // 刷新页面重新请求权限
    window.location.reload()
  }

  return {
    requestCameraPermission,
    checkPermissionStatus,
    permissionStatus,
    showGuide,
    setShowGuide,
    handleRetry,
  }
}