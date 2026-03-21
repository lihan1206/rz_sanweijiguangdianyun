import { ref, reactive } from 'vue'

interface WebSocketState {
  connected: boolean
  connecting: boolean
  error: string | null
}

interface WebSocketMessage {
  type: string
  data: any
}

class WebSocketService {
  private ws: WebSocket | null = null
  private sceneId: number | null = null
  private token: string | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectDelay = 3000
  private messageHandlers: Map<string, ((data: any) => void)[]> = new Map()
  
  public state = reactive<WebSocketState>({
    connected: false,
    connecting: false,
    error: null
  })

  connect(sceneId: number, token: string): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        resolve()
        return
      }

      this.sceneId = sceneId
      this.token = token
      this.state.connecting = true
      this.state.error = null

      const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/${sceneId}`
      this.ws = new WebSocket(wsUrl)

      this.ws.onopen = () => {
        this.state.connected = true
        this.state.connecting = false
        this.reconnectAttempts = 0
        
        // 发送认证消息
        this.send({
          type: 'auth',
          token: this.token
        })
        
        resolve()
      }

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data)
          this.handleMessage(message)
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error)
        }
      }

      this.ws.onclose = () => {
        this.state.connected = false
        this.state.connecting = false
        
        // 尝试重连
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++
          setTimeout(() => {
            if (this.sceneId && this.token) {
              this.connect(this.sceneId, this.token)
            }
          }, this.reconnectDelay)
        }
      }

      this.ws.onerror = (error) => {
        this.state.error = 'WebSocket connection error'
        this.state.connecting = false
        reject(error)
      }
    })
  }

  disconnect() {
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.state.connected = false
    this.state.connecting = false
    this.sceneId = null
    this.token = null
    this.reconnectAttempts = 0
  }

  send(message: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    } else {
      console.warn('WebSocket is not connected')
    }
  }

  on(event: string, handler: (data: any) => void) {
    if (!this.messageHandlers.has(event)) {
      this.messageHandlers.set(event, [])
    }
    this.messageHandlers.get(event)?.push(handler)
  }

  off(event: string, handler: (data: any) => void) {
    const handlers = this.messageHandlers.get(event)
    if (handlers) {
      const index = handlers.indexOf(handler)
      if (index > -1) {
        handlers.splice(index, 1)
      }
    }
  }

  private handleMessage(message: WebSocketMessage) {
    const handlers = this.messageHandlers.get(message.type)
    if (handlers) {
      handlers.forEach(handler => handler(message.data))
    }
  }

  // 便捷方法
  updateView(viewMatrix: number[], cursorPosition: number[]) {
    this.send({
      type: 'user:view_update',
      data: {
        view_matrix: viewMatrix,
        cursor_position: cursorPosition
      }
    })
  }

  updatePointCloudTransform(pointCloudId: number, transform: any) {
    this.send({
      type: 'pointcloud:transform',
      data: {
        point_cloud_id: pointCloudId,
        transform
      }
    })
  }

  updatePointCloudVisibility(pointCloudId: number, visible: boolean) {
    this.send({
      type: 'pointcloud:visibility',
      data: {
        point_cloud_id: pointCloudId,
        visible
      }
    })
  }

  ping() {
    this.send({
      type: 'ping',
      timestamp: Date.now()
    })
  }
}

export const wsService = new WebSocketService()
export default wsService
