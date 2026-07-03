'use client'

import { useEffect, useRef, useState } from 'react'
import Image from 'next/image'
import { Phone, PhoneOff, Mic, MicOff, VideoOff, Video as VideoIcon, User } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useSignalingWebSocket, type SignalingMessage } from '@/hooks/use-signaling-websocket'
import { useWebRTCCall } from '@/hooks/use-webrtc-call'
import type { CallType as WebRTCCallType } from '@/hooks/use-webrtc-call'
import { PLACEHOLDER_AVATAR } from '@/lib/image-url'

export type CallType = WebRTCCallType

export type VideoCallModalProps = {
  callId: string
  callerId: string
  calleeId: string
  callType: CallType
  callerName: string
  callerAvatar: string
  calleeName: string
  calleeAvatar: string
  isInitiator: boolean
  userId: string
  signalingServerUrl: string
  onClose: () => void
  onCallEnded?: () => void
  onStateChange?: (state: 'idle' | 'connecting' | 'ringing' | 'active' | 'ended') => void
}

export function VideoCallModal({
  callId,
  callerId,
  calleeId,
  callType,
  callerName,
  callerAvatar,
  calleeName,
  calleeAvatar,
  isInitiator,
  userId,
  signalingServerUrl,
  onClose,
  onCallEnded,
  onStateChange,
}: VideoCallModalProps) {
  const [incomingOffer, setIncomingOffer] = useState<RTCSessionDescriptionInit | null>(null)
  const targetUserId = isInitiator ? calleeId : callerId
  const otherName = isInitiator ? calleeName : callerName
  const otherAvatar = isInitiator ? calleeAvatar : callerAvatar

  // 处理信令消息
  const handleSignalingMessage = (message: SignalingMessage) => {
    if (message.call_id !== callId) return

    switch (message.type) {
      case 'offer':
        if (!isInitiator && message.payload?.sdp) {
          setIncomingOffer(message.payload.sdp)
        }
        break
      case 'answer':
        if (isInitiator && message.payload?.sdp) {
          webRTC.handleAnswer(message.payload.sdp)
        }
        break
      case 'ice_candidate':
        if (message.payload?.candidate) {
          webRTC.handleIceCandidate(message.payload.candidate)
        }
        break
      case 'user_left':
        webRTC.endCall()
        break
      case 'error':
        console.error('[VideoCall] Signaling error:', message.error)
        break
    }
  }

  const signaling = useSignalingWebSocket({
    signalingServerUrl,
    userId,
    onMessage: handleSignalingMessage,
    onConnected: () => {
      // 连接成功后加入房间
      signaling.send({
        type: 'join_room',
        call_id: callId,
        user_id: userId,
      })

      // 发起方自动发起通话
      if (isInitiator) {
        webRTC.initiateCall()
      }
    },
  })

  const webRTC = useWebRTCCall({
    callId,
    userId,
    callType,
    isInitiator,
    signalingSend: signaling.send,
    targetUserId,
    onCallEnded: () => {
      onCallEnded?.()
    },
    onError: (error) => {
      console.error('[VideoCall] Error:', error)
    },
  })

  useEffect(() => {
    onStateChange?.(webRTC.callState)
  }, [onStateChange, webRTC.callState])

  // 本地视频渲染
  const localVideoRef = useRef<HTMLVideoElement>(null)
  useEffect(() => {
    if (localVideoRef.current && webRTC.localStream) {
      localVideoRef.current.srcObject = webRTC.localStream
    }
  }, [webRTC.localStream])

  // 远程视频渲染
  const remoteVideoRef = useRef<HTMLVideoElement>(null)
  useEffect(() => {
    if (remoteVideoRef.current && webRTC.remoteStream) {
      remoteVideoRef.current.srcObject = webRTC.remoteStream
    }
  }, [webRTC.remoteStream])

  // 接听按钮
  const handleAccept = () => {
    if (incomingOffer) {
      webRTC.answerCall(incomingOffer)
      setIncomingOffer(null)
    }
  }

  // 拒绝按钮
  const handleReject = () => {
    webRTC.endCall()
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 bg-black flex flex-col">
      {/* 视频通话视图 */}
      {callType === 'video' && (
        <div className="flex-1 relative">
          {/* 远程视频（主视图） */}
          <video
            ref={remoteVideoRef}
            autoPlay
            playsInline
            className="w-full h-full object-cover"
          />

          {/* 本地视频（小窗口） */}
          <div className="absolute top-4 right-4 w-32 h-48 rounded-lg overflow-hidden bg-muted shadow-lg">
            <video
              ref={localVideoRef}
              autoPlay
              playsInline
              muted
              className="w-full h-full object-cover"
            />
            {webRTC.isCameraOff && (
              <div className="absolute inset-0 bg-muted flex items-center justify-center">
                <User className="w-8 h-8 text-muted-foreground" />
              </div>
            )}
          </div>

          {/* 通话状态提示 */}
          {webRTC.callState !== 'active' && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/50">
              <div className="text-center">
                <div className="w-20 h-20 rounded-full overflow-hidden mx-auto mb-4 bg-muted">
                  <Image
                    src={otherAvatar || PLACEHOLDER_AVATAR}
                    alt={otherName}
                    width={80}
                    height={80}
                    className="object-cover"
                  />
                </div>
                <p className="text-white text-lg font-medium">{otherName}</p>
                <p className="text-white/70 text-sm mt-2">
                  {webRTC.callState === 'connecting' && '正在连接...'}
                  {webRTC.callState === 'ringing' && '正在呼叫...'}
                  {webRTC.callState === 'idle' && '准备通话...'}
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 语音通话视图 */}
      {callType === 'audio' && (
        <div className="flex-1 flex items-center justify-center bg-gradient-to-b from-muted to-background">
          <div className="text-center">
            <div className="w-24 h-24 rounded-full overflow-hidden mx-auto mb-6 bg-secondary ring-4 ring-primary/20">
              <Image
                src={otherAvatar || PLACEHOLDER_AVATAR}
                alt={otherName}
                width={96}
                height={96}
                className="object-cover"
              />
            </div>
            <p className="text-foreground text-xl font-medium">{otherName}</p>
            <p className="text-muted-foreground text-sm mt-3">
              {webRTC.callState === 'active' ? '通话中' : '正在连接...'}
            </p>
          </div>
        </div>
      )}

      {/* 呼入提示（仅非发起方） */}
      {!isInitiator && incomingOffer && webRTC.callState !== 'active' && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/70 animate-fade-in">
          <div className="text-center bg-background rounded-2xl p-8 shadow-xl">
            <div className="w-20 h-20 rounded-full overflow-hidden mx-auto mb-4 bg-secondary">
              <Image
                src={callerAvatar || PLACEHOLDER_AVATAR}
                alt={callerName}
                width={80}
                height={80}
                className="object-cover"
              />
            </div>
            <p className="text-foreground text-lg font-medium mb-2">{callerName}</p>
            <p className="text-muted-foreground text-sm mb-6">
              {callType === 'video' ? '邀请你进行视频通话' : '邀请你进行语音通话'}
            </p>
            <div className="flex gap-4 justify-center">
              <button
                onClick={handleReject}
                className="w-14 h-14 rounded-full bg-rose-500 hover:bg-rose-600 flex items-center justify-center transition-colors"
              >
                <PhoneOff className="w-6 h-6 text-white" />
              </button>
              <button
                onClick={handleAccept}
                className="w-14 h-14 rounded-full bg-green-500 hover:bg-green-600 flex items-center justify-center transition-colors"
              >
                <Phone className="w-6 h-6 text-white" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 控制栏 */}
      <div className="flex-shrink-0 bg-background/90 backdrop-blur px-6 py-4 safe-area-bottom">
        <div className="flex items-center justify-center gap-6">
          {/* 麦克风开关 */}
          <button
            onClick={webRTC.toggleMute}
            className={cn(
              'w-12 h-12 rounded-full flex items-center justify-center transition-all',
              webRTC.isMuted
                ? 'bg-rose-500 text-white'
                : 'bg-secondary text-foreground hover:bg-secondary/80'
            )}
            aria-label={webRTC.isMuted ? '取消静音' : '静音'}
          >
            {webRTC.isMuted ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
          </button>

          {/* 摄像头开关（仅视频通话） */}
          {callType === 'video' && (
            <button
              onClick={webRTC.toggleCamera}
              className={cn(
                'w-12 h-12 rounded-full flex items-center justify-center transition-all',
                webRTC.isCameraOff
                  ? 'bg-rose-500 text-white'
                  : 'bg-secondary text-foreground hover:bg-secondary/80'
              )}
              aria-label={webRTC.isCameraOff ? '开启摄像头' : '关闭摄像头'}
            >
              {webRTC.isCameraOff ? <VideoOff className="w-5 h-5" /> : <VideoIcon className="w-5 h-5" />}
            </button>
          )}

          {/* 挂断 */}
          <button
            onClick={webRTC.endCall}
            className="w-16 h-16 rounded-full bg-rose-500 hover:bg-rose-600 flex items-center justify-center transition-colors"
            aria-label="挂断"
          >
            <PhoneOff className="w-6 h-6 text-white" />
          </button>
        </div>
      </div>
    </div>
  )
}
