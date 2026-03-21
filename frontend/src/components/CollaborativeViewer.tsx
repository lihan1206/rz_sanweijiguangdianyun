import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { Alert, Card, Space, Statistic, Tag, Typography } from 'antd';
import { UserOutlined, SyncOutlined } from '@ant-design/icons';
import type { CollaborativeSession, PointCloud, SessionUserInfo } from '../types';
import { api } from '../services/api';

const { Title, Text } = Typography;

interface Props {
  session: CollaborativeSession | null;
  currentUserId: number;
}

interface UserPointCloud {
  userId: number;
  username: string;
  points: number[][];
  color: string;
  pointCloudId: number;
}

const USER_COLORS = [
  '#1677ff', // 蓝色 - 当前用户
  '#52c41a', // 绿色
  '#fa8c16', // 橙色
  '#eb2f96', // 粉色
  '#722ed1', // 紫色
  '#13c2c2', // 青色
];

export function CollaborativeViewer({ session, currentUserId }: Props): JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const animationIdRef = useRef<number>(0);
  const wsRef = useRef<WebSocket | null>(null);

  const [pointClouds, setPointClouds] = useState<UserPointCloud[]>([]);
  const [onlineUsers, setOnlineUsers] = useState<SessionUserInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState(false);

  // 初始化Three.js场景
  useEffect(() => {
    if (!containerRef.current) return;

    const width = containerRef.current.clientWidth;
    const height = 500;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#f0f5ff');
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(65, width / height, 0.1, 1000);
    camera.position.set(30, 30, 30);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    containerRef.current.innerHTML = '';
    containerRef.current.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controlsRef.current = controls;

    const grid = new THREE.GridHelper(60, 40, '#8aa6bf', '#d6e4f0');
    scene.add(grid);

    const axesHelper = new THREE.AxesHelper(20);
    scene.add(axesHelper);

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(30, 40, 20);
    scene.add(directionalLight);

    const animate = (): void => {
      animationIdRef.current = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    const handleResize = (): void => {
      if (!containerRef.current || !camera || !renderer) return;
      const newWidth = containerRef.current.clientWidth;
      camera.aspect = newWidth / height;
      camera.updateProjectionMatrix();
      renderer.setSize(newWidth, height);
    };
    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(animationIdRef.current);
      window.removeEventListener('resize', handleResize);
      controls.dispose();
      renderer.dispose();
    };
  }, []);

  // 加载会话中的点云
  const loadSessionPointClouds = async (): Promise<void> => {
    if (!session) return;
    setLoading(true);
    setError(null);
    try {
      const { data: allPointClouds } = await api.get<PointCloud[]>('/pointclouds');
      const sessionPointClouds = allPointClouds.filter(pc => pc.session_id === session.id && !pc.is_deleted);
      
      const userPointClouds: UserPointCloud[] = [];
      for (const pc of sessionPointClouds) {
        try {
          const { data: sample } = await api.get<{ points: number[][] }>(`/pointclouds/${pc.id}/sample`, {
            params: { limit: 5000 }
          });
          const colorIndex = pc.created_by === currentUserId ? 0 : (pc.created_by % (USER_COLORS.length - 1)) + 1;
          userPointClouds.push({
            userId: pc.created_by,
            username: `用户${pc.created_by}`,
            points: sample.points,
            color: USER_COLORS[colorIndex],
            pointCloudId: pc.id,
          });
        } catch (e) {
          console.warn(`无法加载点云 ${pc.id}:`, e);
        }
      }
      setPointClouds(userPointClouds);
    } catch (error: any) {
      setError(error.response?.data?.detail || '加载点云数据失败');
    } finally {
      setLoading(false);
    }
  };

  // 加载在线用户
  const loadOnlineUsers = async (): Promise<void> => {
    if (!session) return;
    try {
      const { data } = await api.get<SessionUserInfo[]>(`/collaboration/sessions/${session.id}/users`);
      setOnlineUsers(data);
    } catch (error) {
      console.error('加载在线用户失败:', error);
    }
  };

  // WebSocket连接
  useEffect(() => {
    if (!session) return;

    const wsUrl = `ws://localhost:8000/api/v1/collaboration/ws/${session.id}/${currentUserId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket连接成功');
      setWsConnected(true);
    };

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      handleWebSocketMessage(message);
    };

    ws.onclose = () => {
      console.log('WebSocket连接关闭');
      setWsConnected(false);
    };

    ws.onerror = (error) => {
      console.error('WebSocket错误:', error);
      setWsConnected(false);
    };

    return () => {
      ws.close();
    };
  }, [session?.id, currentUserId]);

  // 处理WebSocket消息
  const handleWebSocketMessage = (message: any): void => {
    switch (message.type) {
      case 'pointcloud_updated':
        void loadSessionPointClouds();
        break;
      case 'user_joined':
      case 'user_left':
        void loadOnlineUsers();
        break;
      case 'task_completed':
        void loadSessionPointClouds();
        break;
    }
  };

  // 更新点云渲染
  useEffect(() => {
    if (!sceneRef.current) return;

    const scene = sceneRef.current;
    const oldClouds = scene.children.filter(child => child.userData.isUserPointCloud);
    oldClouds.forEach(cloud => {
      scene.remove(cloud);
      if (cloud instanceof THREE.Points) {
        cloud.geometry.dispose();
        if (cloud.material instanceof THREE.Material) {
          cloud.material.dispose();
        }
      }
    });

    pointClouds.forEach((userPc) => {
      if (userPc.points.length === 0) return;

      const positions = new Float32Array(userPc.points.length * 3);
      userPc.points.forEach((point, index) => {
        positions[index * 3] = point[0];
        positions[index * 3 + 1] = point[1];
        positions[index * 3 + 2] = point[2];
      });

      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

      const material = new THREE.PointsMaterial({
        color: userPc.color,
        size: 0.15,
        sizeAttenuation: true,
        transparent: true,
        opacity: 0.9,
      });

      const cloud = new THREE.Points(geometry, material);
      cloud.userData.isUserPointCloud = true;
      cloud.userData.userId = userPc.userId;
      scene.add(cloud);
    });
  }, [pointClouds]);

  // 会话变化时重新加载数据
  useEffect(() => {
    if (session) {
      void loadSessionPointClouds();
      void loadOnlineUsers();
    } else {
      setPointClouds([]);
      setOnlineUsers([]);
    }
  }, [session]);

  if (!session) {
    return (
      <Card bordered={false}>
        <Alert
          type="info"
          message="请选择或创建一个协同会话"
          description="加入协同会话后，可以与其他用户实时共享点云处理结果"
          showIcon
        />
      </Card>
    );
  }

  return (
    <Card
      title={
        <Space>
          <span>协同可视化 - {session.session_name}</span>
          {wsConnected ? (
            <Tag color="success" icon={<SyncOutlined spin />}>已连接</Tag>
          ) : (
            <Tag color="warning">连接中...</Tag>
          )}
        </Space>
      }
      bordered={false}
      extra={
        <Space>
          <Statistic
            title="参与者"
            value={onlineUsers.length}
            prefix={<UserOutlined />}
            valueStyle={{ fontSize: 16 }}
          />
          <Statistic
            title="点云数据"
            value={pointClouds.length}
            valueStyle={{ fontSize: 16 }}
          />
        </Space>
      }
    >
      {error && (
        <Alert
          type="error"
          message={error}
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      <div style={{ marginBottom: 16 }}>
        <Text type="secondary">参与者颜色标识：</Text>
        <Space wrap style={{ marginLeft: 8 }}>
          {onlineUsers.map((user, index) => {
            const colorIndex = user.user_id === currentUserId ? 0 : (user.user_id % (USER_COLORS.length - 1)) + 1;
            return (
              <Tag
                key={user.user_id}
                style={{
                  backgroundColor: USER_COLORS[colorIndex],
                  color: '#fff',
                  border: 'none',
                }}
              >
                {user.username}
                {user.user_id === currentUserId && ' (我)'}
              </Tag>
            );
          })}
        </Space>
      </div>

      <div
        ref={containerRef}
        style={{
          width: '100%',
          height: 500,
          borderRadius: 8,
          overflow: 'hidden',
          border: '1px solid #e8e8e8',
        }}
      />

      <div style={{ marginTop: 16 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          💡 提示：在协同会话中创建的处理任务完成后，所有参与者都能实时看到更新后的点云数据。
          您可以通过鼠标左键旋转、滚轮缩放、右键平移来查看3D点云。
        </Text>
      </div>
    </Card>
  );
}
