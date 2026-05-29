/**
 * WebRTC call management hook
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import type { SignalingMessage } from './use-signaling-websocket'

// ICE 服务器配置（需要配置 coturn 或使用公共 STUN）
const ICE_SERVERS: RTCIceServer[] = [
  { urls: 'stun:stun.l.google.com:19302' },
  { urls: 'stun:stun1.l.google.com:19302' },
  // 如果有自建的 TURN 服务器，可以添加：
  // { urls: 'turn:your-turn-server:3478', username: '...', credential: '...' }
]

export type CallState = 'idle' | 'connecting' | 'ringing' | 'active' | 'ended'

export type CallType = 'audio' | 'video'

export type UseWebRTCCallOptions = {
  callId: string
  userId: string
  callType: CallType
  isInitiator: boolean
  signalingSend: (message: SignalingMessage) => void
  targetUserId: string
  onCallEnded?: () => void
  onError?: (error: string) => void
}

export function useWebRTCCall({
  callId,
  userId,
  callType,
  isInitiator,
  signalingSend,
  targetUserId,
  onCallEnded,
  onError,
}: UseWebRTCCallOptions) {
  const [callState, setCallState] = useState<CallState>('idle')
  const [localStream, setLocalStream] = useState<MediaStream | null>(null)
  const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null)
  const [isMuted, setIsMuted] = useState(false)
  const [isCameraOff, setIsCameraOff] = useState(callType === 'audio')

  const pcRef = useRef<RTCPeerConnection | null>(null)
  const localStreamRef = useRef<MediaStream | null>(null)

  // 创建 RTCPeerConnection
  const createPeerConnection = useCallback(() => {
    const pc = new RTCPeerConnection({
      iceServers: ICE_SERVERS,
    })

    // 处理远程流
    pc.ontrack = (event) => {
      console.log('[WebRTC] Received remote track:', event.track.kind)
      const stream = new MediaStream()
      stream.addTrack(event.track)
      setRemoteStream(stream)
    }

    // 处理 ICE candidate
    pc.onicecandidate = (event) => {
      if (event.candidate) {
        console.log('[WebRTC] ICE candidate generated')
        signalingSend({
          type: 'ice_candidate',
          call_id: callId,
          user_id: userId,
          payload: {
            candidate: event.candidate.toJSON(),
            target_user_id: targetUserId,
          },
        })
      }
    }

    // 连接状态变化
    pc.onconnectionstatechange = () => {
      console.log('[WebRTC] Connection state:', pc.connectionState)
      if (pc.connectionState === 'connected') {
        setCallState('active')
      } else if (pc.connectionState === 'disconnected' || pc.connectionState === 'failed') {
        setCallState('ended')
        onCallEnded?.()
      }
    }

    pcRef.current = pc
    return pc
  }, [callId, userId, targetUserId, signalingSend, onCallEnded])

  // 获取本地媒体流
  const getLocalStream = useCallback(async () => {
    try {
      const constraints: MediaStreamConstraints = {
        audio: true,
        video: callType === 'video',
      }

      const stream = await navigator.mediaDevices.getUserMedia(constraints)
      localStreamRef.current = stream
      setLocalStream(stream)

      // 将本地轨道添加到 PeerConnection
      if (pcRef.current) {
        stream.getTracks().forEach((track) => {
          pcRef.current?.addTrack(track, stream)
        })
      }

      return stream
    } catch (error) {
      console.error('[WebRTC] Failed to get media stream:', error)
      onError?.('无法获取摄像头/麦克风')
      throw error
    }
  }, [callType, onError])

  // 发起通话（创建 offer）
  const initiateCall = useCallback(async () => {
    try {
      setCallState('connecting')
      const pc = createPeerConnection()
      await getLocalStream()

      const offer = await pc.createOffer({
        offerToReceiveAudio: true,
        offerToReceiveVideo: callType === 'video',
      })
      await pc.setLocalDescription(offer)

      signalingSend({
        type: 'offer',
        call_id: callId,
        user_id: userId,
        payload: {
          sdp: offer,
          target_user_id: targetUserId,
        },
      })

      console.log('[WebRTC] Offer sent')
    } catch (error) {
      console.error('[WebRTC] Failed to initiate call:', error)
      setCallState('ended')
      onError?.('发起通话失败')
    }
  }, [createPeerConnection, getLocalStream, callId, userId, targetUserId, callType, signalingSend, onError])

  // 接听通话（创建 answer）
  const answerCall = useCallback(async (offer: RTCSessionDescriptionInit) => {
    try {
      setCallState('connecting')
      const pc = createPeerConnection()
      await getLocalStream()

      await pc.setRemoteDescription(new RTCSessionDescription(offer))

      const answer = await pc.createAnswer()
      await pc.setLocalDescription(answer)

      signalingSend({
        type: 'answer',
        call_id: callId,
        user_id: userId,
        payload: {
          sdp: answer,
          target_user_id: targetUserId,
        },
      })

      console.log('[WebRTC] Answer sent')
    } catch (error) {
      console.error('[WebRTC] Failed to answer call:', error)
      setCallState('ended')
      onError?.('接听通话失败')
    }
  }, [createPeerConnection, getLocalStream, callId, userId, targetUserId, signalingSend, onError])

  // 处理 answer
  const handleAnswer = useCallback(async (answer: RTCSessionDescriptionInit) => {
    if (pcRef.current) {
      await pcRef.current.setRemoteDescription(new RTCSessionDescription(answer))
      console.log('[WebRTC] Remote description set from answer')
    }
  }, [])

  // 处理 ICE candidate
  const handleIceCandidate = useCallback(async (candidate: RTCIceCandidateInit) => {
    if (pcRef.current) {
      await pcRef.current.addIceCandidate(new RTCIceCandidate(candidate))
      console.log('[WebRTC] ICE candidate added')
    }
  }, [])

  // 结束通话
  const endCall = useCallback(() => {
    // 停止本地流
    if (localStreamRef.current) {
      localStreamRef.current.getTracks().forEach((track) => track.stop())
      localStreamRef.current = null
      setLocalStream(null)
    }

    // 关闭 PeerConnection
    if (pcRef.current) {
      pcRef.current.close()
      pcRef.current = null
    }

    // 发送离开消息
    signalingSend({
      type: 'leave_room',
      call_id: callId,
      user_id: userId,
    })

    setCallState('ended')
    setRemoteStream(null)
    onCallEnded?.()
  }, [callId, userId, signalingSend, onCallEnded])

  // 切换麦克风
  const toggleMute = useCallback(() => {
    if (localStreamRef.current) {
      const audioTrack = localStreamRef.current.getAudioTracks()[0]
      if (audioTrack) {
        audioTrack.enabled = !audioTrack.enabled
        setIsMuted(!audioTrack.enabled)
      }
    }
  }, [])

  // 切换摄像头
  const toggleCamera = useCallback(async () => {
    if (callType === 'audio') return

    if (localStreamRef.current) {
      const videoTrack = localStreamRef.current.getVideoTracks()[0]
      if (videoTrack) {
        videoTrack.enabled = !videoTrack.enabled
        setIsCameraOff(!videoTrack.enabled)
      }
    }
  }, [callType])

  // 清理
  useEffect(() => {
    return () => {
      if (localStreamRef.current) {
        localStreamRef.current.getTracks().forEach((track) => track.stop())
      }
      if (pcRef.current) {
        pcRef.current.close()
      }
    }
  }, [])

  return {
    callState,
    localStream,
    remoteStream,
    isMuted,
    isCameraOff,
    initiateCall,
    answerCall,
    handleAnswer,
    handleIceCandidate,
    endCall,
    toggleMute,
    toggleCamera,
  }
}