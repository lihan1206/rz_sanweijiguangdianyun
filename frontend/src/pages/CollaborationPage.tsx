import { Badge, Button, Card, Form, Input, InputNumber, List, message, Modal, Popconfirm, Space, Spin, Table, Tag } from 'antd';
import { DeleteOutlined, PlusOutlined, TeamOutlined, UserOutlined, VideoCameraOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

import { api } from '../services/api';
import type { CollaborationScene, PointCloud, SceneListItem, ScenePointCloud, WebSocketMessage } from '../types';

interface Props {
  user: { id: number; username: string; role: string };
}

interface CollaborativeViewerProps {
  pointclouds: ScenePointCloud[];
  sessionToken: string;
  sceneId: number;
}

function CollaborativeViewer({ pointclouds }: CollaborativeViewerProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const pointCloudObjectsRef = useRef<Map<number, THREE.Points>>(new Map());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!containerRef.current) return;

    const width = containerRef.current.clientWidth;
    const height = 500;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#1a1a2e');
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 10000);
    camera.position.set(50, 50, 50);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(window.devicePixelRatio);
    containerRef.current.innerHTML = '';
    containerRef.current.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controlsRef.current = controls;

    const grid = new THREE.GridHelper(100, 50, '#444466', '#333355');
    scene.add(grid);

    const axesHelper = new THREE.AxesHelper(20);
    scene.add(axesHelper);

    const ambient = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambient);

    const directional = new THREE.DirectionalLight(0xffffff, 0.8);
    directional.position.set(50, 100, 50);
    scene.add(directional);

    let animationId = 0;
    const animate = (): void => {
      animationId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    const onResize = (): void => {
      if (!containerRef.current) return;
      const newWidth = containerRef.current.clientWidth;
      camera.aspect = newWidth / height;
      camera.updateProjectionMatrix();
      renderer.setSize(newWidth, height);
    };
    window.addEventListener('resize', onResize);

    setLoading(false);

    return () => {
      cancelAnimationFrame(animationId);
      window.removeEventListener('resize', onResize);
      controls.dispose();
      renderer.dispose();
    };
  }, []);

  useEffect(() => {
    if (!sceneRef.current || pointclouds.length === 0) return;

    pointCloudObjectsRef.current.forEach((obj: THREE.Points) => {
      sceneRef.current?.remove(obj);
      obj.geometry.dispose();
      (obj.material as THREE.Material).dispose();
    });
    pointCloudObjectsRef.current.clear();

    pointclouds.forEach(async (spc: ScenePointCloud) => {
      if (!spc.visible || !sceneRef.current) return;

      try {
        const { data } = await api.get<{ points: number[][] }>(`/pointclouds/${spc.pointcloud_id}/sample?limit=50000`);
        const points = data.points;

        if (points.length === 0) return;

        const positions = new Float32Array(points.length * 3);
        const colors = new Float32Array(points.length * 3);

        const baseColor = spc.color ? new THREE.Color(spc.color) : new THREE.Color('#00d4ff');
        points.forEach((point: number[], index: number) => {
          positions[index * 3] = point[0];
          positions[index * 3 + 1] = point[2];
          positions[index * 3 + 2] = point[1];

          colors[index * 3] = baseColor.r;
          colors[index * 3 + 1] = baseColor.g;
          colors[index * 3 + 2] = baseColor.b;
        });

        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

        const material = new THREE.PointsMaterial({
          size: 0.5,
          vertexColors: true,
          sizeAttenuation: true,
          transparent: true,
          opacity: spc.opacity,
        });

        const pointCloud = new THREE.Points(geometry, material);
        sceneRef.current.add(pointCloud);
        pointCloudObjectsRef.current.set(spc.pointcloud_id, pointCloud);
      } catch (error) {
        console.error('Failed to load pointcloud:', error);
      }
    });
  }, [pointclouds]);

  return (
    <div style={{ position: 'relative' }}>
      {loading && (
        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', zIndex: 10 }}>
          <Spin size="large" tip="加载点云数据..." />
        </div>
      )}
      <div ref={containerRef} style={{ width: '100%', height: 500, borderRadius: 8, overflow: 'hidden' }} />
    </div>
  );
}

export function CollaborationPage({ user }: Props): JSX.Element {
  const [scenes, setScenes] = useState<SceneListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentScene, setCurrentScene] = useState<CollaborationScene | null>(null);
  const [sessionToken, setSessionToken] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [pointclouds, setPointclouds] = useState<PointCloud[]>([]);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [addPcModalVisible, setAddPcModalVisible] = useState(false);
  const [createForm] = Form.useForm();
  const wsRef = useRef<WebSocket | null>(null);

  const loadScenes = async (): Promise<void> => {
    setLoading(true);
    try {
      const { data } = await api.get<SceneListItem[]>('/scenes');
      setScenes(data);
    } catch {
      message.error('加载场景列表失败');
    } finally {
      setLoading(false);
    }
  };

  const loadPointclouds = async (): Promise<void> => {
    try {
      const { data } = await api.get<PointCloud[]>('/pointclouds');
      setPointclouds(data);
    } catch {
      message.error('加载点云列表失败');
    }
  };

  useEffect(() => {
    void loadScenes();
    void loadPointclouds();
  }, []);

  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const connectWebSocket = (token: string, sceneId: number): void => {
    const wsBaseUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/api/v1';
    const wsUrl = `${wsBaseUrl}/scenes/ws/${sceneId}?session_token=${token}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
      message.success('WebSocket 连接成功');
    };

    ws.onmessage = (event) => {
      const msg: WebSocketMessage = JSON.parse(event.data);
      handleWebSocketMessage(msg);
    };

    ws.onclose = () => {
      setWsConnected(false);
      message.info('WebSocket 连接已断开');
    };

    ws.onerror = () => {
      setWsConnected(false);
      message.error('WebSocket 连接错误');
    };
  };

  const handleWebSocketMessage = (msg: WebSocketMessage): void => {
    switch (msg.event_type) {
      case 'user_joined':
        message.info(`${msg.username} 加入了场景`);
        void loadSceneDetail(msg.scene_id);
        break;
      case 'user_left':
        message.info(`${msg.username} 离开了场景`);
        void loadSceneDetail(msg.scene_id);
        break;
      case 'pointcloud_update':
        void loadSceneDetail(msg.scene_id);
        break;
      case 'task_completed':
        message.success(`${msg.username} 完成了处理任务`);
        void loadSceneDetail(msg.scene_id);
        break;
      case 'task_progress':
        if (msg.progress !== undefined) {
          message.info(`任务 ${msg.task_id} 进度: ${msg.progress}%`);
        }
        break;
    }
  };

  const loadSceneDetail = async (sceneId: number): Promise<void> => {
    try {
      const { data } = await api.get<CollaborationScene>(`/scenes/${sceneId}`);
      setCurrentScene(data);
    } catch {
      message.error('加载场景详情失败');
    }
  };

  const handleJoinScene = async (sceneId: number): Promise<void> => {
    try {
      const { data } = await api.post<{ session_token: string; scene: CollaborationScene; message: string }>(
        `/scenes/${sceneId}/join`
      );
      setSessionToken(data.session_token);
      setCurrentScene(data.scene);
      connectWebSocket(data.session_token, sceneId);
      message.success(data.message);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || '加入场景失败');
    }
  };

  const handleLeaveScene = async (): Promise<void> => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (sessionToken && currentScene) {
      try {
        await api.post(`/scenes/${currentScene.id}/leave?session_token=${sessionToken}`);
      } catch {
        // ignore
      }
    }
    setSessionToken(null);
    setCurrentScene(null);
    setWsConnected(false);
  };

  const handleCreateScene = async (values: { name: string; description?: string; max_users?: number }): Promise<void> => {
    try {
      await api.post('/scenes', values);
      message.success('场景创建成功');
      setCreateModalVisible(false);
      createForm.resetFields();
      void loadScenes();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || '创建场景失败');
    }
  };

  const handleAddPointcloud = async (pointcloudId: number): Promise<void> => {
    if (!currentScene) return;
    try {
      await api.post(`/scenes/${currentScene.id}/pointclouds`, { pointcloud_id: pointcloudId });
      message.success('点云已添加到场景');
      void loadSceneDetail(currentScene.id);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || '添加点云失败');
    }
  };

  const handleRemovePointcloud = async (spcId: number): Promise<void> => {
    if (!currentScene) return;
    try {
      await api.delete(`/scenes/${currentScene.id}/pointclouds/${spcId}`);
      message.success('点云已从场景移除');
      void loadSceneDetail(currentScene.id);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || '移除点云失败');
    }
  };

  const columns: ColumnsType<SceneListItem> = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '场景名称', dataIndex: 'name' },
    { title: '描述', dataIndex: 'description', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'is_active',
      render: (v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? '活跃' : '已关闭'}</Tag>,
    },
    { title: '点云数', dataIndex: 'pointcloud_count', width: 80 },
    {
      title: '在线用户',
      dataIndex: 'active_users',
      width: 100,
      render: (v: number, record: SceneListItem) => (
        <Space>
          <Badge status={v > 0 ? 'success' : 'default'} />
          <span>{v}/{record.max_users}</span>
        </Space>
      ),
    },
    { title: '创建者', dataIndex: 'created_by_name', width: 100 },
    {
      title: '操作',
      width: 120,
      render: (_: unknown, record: SceneListItem) => (
        <Button type="link" onClick={() => handleJoinScene(record.id)} icon={<VideoCameraOutlined />}>
          进入
        </Button>
      ),
    },
  ];

  if (currentScene && sessionToken) {
    return (
      <div style={{ padding: 24 }}>
        <Card
          title={
            <Space>
              <TeamOutlined />
              <span>{currentScene.name}</span>
              <Tag color={wsConnected ? 'green' : 'red'}>{wsConnected ? '已连接' : '未连接'}</Tag>
            </Space>
          }
          extra={
            <Space>
              <Button icon={<PlusOutlined />} onClick={() => setAddPcModalVisible(true)}>
                添加点云
              </Button>
              <Button danger onClick={handleLeaveScene}>
                离开场景
              </Button>
            </Space>
          }
        >
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            <Card size="small" title="在线用户">
              <Space>
                {currentScene.active_sessions.map((s) => (
                  <Tag key={s.id} icon={<UserOutlined />} color="blue">
                    {s.username}
                  </Tag>
                ))}
                {currentScene.active_sessions.length === 0 && <span style={{ color: '#999' }}>暂无其他在线用户</span>}
              </Space>
            </Card>

            <CollaborativeViewer
              pointclouds={currentScene.pointclouds}
              sessionToken={sessionToken}
              sceneId={currentScene.id}
            />

            <Card size="small" title="场景点云列表">
              <Table
                dataSource={currentScene.pointclouds}
                rowKey="id"
                size="small"
                pagination={false}
                columns={[
                  { title: '点云名称', dataIndex: 'pointcloud_name' },
                  { title: '颜色', dataIndex: 'color', render: (v: string | null) => v || '默认' },
                  { title: '透明度', dataIndex: 'opacity' },
                  {
                    title: '可见',
                    dataIndex: 'visible',
                    render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '是' : '否'}</Tag>,
                  },
                  { title: '添加者', dataIndex: 'added_by_name' },
                  {
                    title: '操作',
                    render: (_: unknown, record: ScenePointCloud) => (
                      <Popconfirm title="确定移除此点云？" onConfirm={() => handleRemovePointcloud(record.id)}>
                        <Button type="link" danger icon={<DeleteOutlined />}>
                          移除
                        </Button>
                      </Popconfirm>
                    ),
                  },
                ]}
              />
            </Card>
          </Space>
        </Card>

        <Modal
          title="添加点云到场景"
          open={addPcModalVisible}
          onCancel={() => setAddPcModalVisible(false)}
          footer={null}
          width={600}
        >
          <List
            dataSource={pointclouds.filter((pc) => !currentScene.pointclouds.some((spc) => spc.pointcloud_id === pc.id))}
            renderItem={(item: PointCloud) => (
              <List.Item
                actions={[
                  <Button key="add" type="link" onClick={() => handleAddPointcloud(item.id)}>
                    添加
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={item.name}
                  description={`${item.file_format.toUpperCase()} | ${item.points_count?.toLocaleString() || '未知'} 点`}
                />
              </List.Item>
            )}
          />
        </Modal>
      </div>
    );
  }

  return (
    <div style={{ padding: 24 }}>
      <Card
        title={
          <Space>
            <TeamOutlined />
            <span>协同场景</span>
          </Space>
        }
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalVisible(true)}>
            创建场景
          </Button>
        }
      >
        <Table
          dataSource={scenes}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      <Modal
        title="创建协同场景"
        open={createModalVisible}
        onCancel={() => setCreateModalVisible(false)}
        onOk={() => createForm.submit()}
      >
        <Form form={createForm} onFinish={handleCreateScene} layout="vertical">
          <Form.Item name="name" label="场景名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="max_users" label="最大用户数" initialValue={10}>
            <InputNumber min={1} max={100} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
