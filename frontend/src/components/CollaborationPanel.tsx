import {
  Button,
  Card,
  Col,
  Form,
  Input,
  List,
  Modal,
  Row,
  Space,
  Statistic,
  Tag,
  Tooltip,
  Typography
} from 'antd';
import {
  DeleteOutlined,
  PlusOutlined,
  TeamOutlined,
  UserOutlined,
  VideoCameraOutlined
} from '@ant-design/icons';
import { useEffect, useState } from 'react';
import type { CollaborativeSession, SessionUserInfo, User } from '../types';
import { api } from '../services/api';

const { Title, Text, Paragraph } = Typography;

interface Props {
  user: User;
  canManage: boolean;
  onSessionSelect: (session: CollaborativeSession) => void;
  currentSessionId: number | null;
}

export function CollaborationPanel({ user, canManage, onSessionSelect, currentSessionId }: Props): JSX.Element {
  const [sessions, setSessions] = useState<CollaborativeSession[]>([]);
  const [loading, setLoading] = useState(false);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [usersModalOpen, setUsersModalOpen] = useState(false);
  const [selectedSession, setSelectedSession] = useState<CollaborativeSession | null>(null);
  const [sessionUsers, setSessionUsers] = useState<SessionUserInfo[]>([]);
  const [createForm] = Form.useForm();

  const loadSessions = async (): Promise<void> => {
    setLoading(true);
    try {
      const { data } = await api.get<CollaborativeSession[]>('/collaboration/sessions');
      setSessions(data);
    } catch (error) {
      console.error('加载会话失败:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadSessions();
  }, []);

  const handleCreateSession = async (values: { session_name: string; description: string; max_users: number }): Promise<void> => {
    try {
      await api.post('/collaboration/sessions', values);
      setCreateModalOpen(false);
      createForm.resetFields();
      await loadSessions();
    } catch (error: any) {
      console.error('创建会话失败:', error);
    }
  };

  const handleJoinSession = async (session: CollaborativeSession): Promise<void> => {
    try {
      await api.post('/collaboration/join', { session_id: session.id });
      setSelectedSession(session);
      onSessionSelect(session);
    } catch (error: any) {
      console.error('加入会话失败:', error);
    }
  };

  const handleLeaveSession = async (sessionId: number): Promise<void> => {
    try {
      await api.post(`/collaboration/leave/${sessionId}`);
      if (currentSessionId === sessionId) {
        setSelectedSession(null);
        onSessionSelect(null as unknown as CollaborativeSession);
      }
      await loadSessions();
    } catch (error: any) {
      console.error('离开会话失败:', error);
    }
  };

  const loadSessionUsers = async (sessionId: number): Promise<void> => {
    try {
      const { data } = await api.get<SessionUserInfo[]>(`/collaboration/sessions/${sessionId}/users`);
      setSessionUsers(data);
      setUsersModalOpen(true);
    } catch (error: any) {
      console.error('加载用户失败:', error);
    }
  };

  const getStatusTag = (session: CollaborativeSession): JSX.Element => {
    if (currentSessionId === session.id) {
      return <Tag color="success">当前会话</Tag>;
    }
    if (session.current_users >= session.max_users) {
      return <Tag color="red">已满</Tag>;
    }
    return <Tag color="blue">可加入</Tag>;
  };

  return (
    <Card
      title={
        <Space>
          <VideoCameraOutlined />
          <span>协同处理会话</span>
        </Space>
      }
      bordered={false}
      extra={
        canManage && (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateModalOpen(true)}
            size="small"
          >
            创建会话
          </Button>
        )
      }
    >
      <List
        loading={loading}
        dataSource={sessions}
        locale={{ emptyText: '暂无协同会话，创建一个开始协作吧！' }}
        renderItem={(session) => (
          <List.Item
            actions={[
              currentSessionId === session.id ? (
                <Button
                  danger
                  size="small"
                  onClick={() => void handleLeaveSession(session.id)}
                >
                  离开
                </Button>
              ) : (
                <Button
                  type="primary"
                  size="small"
                  onClick={() => void handleJoinSession(session)}
                  disabled={session.current_users >= session.max_users}
                >
                  加入
                </Button>
              ),
              <Button
                size="small"
                icon={<TeamOutlined />}
                onClick={() => void loadSessionUsers(session.id)}
              >
                {session.current_users}/{session.max_users}
              </Button>
            ]}
          >
            <List.Item.Meta
              avatar={<UserOutlined />}
              title={
                <Space>
                  <Text strong>{session.session_name}</Text>
                  {getStatusTag(session)}
                </Space>
              }
              description={
                <Space direction="vertical" size={0} style={{ width: '100%' }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {session.description || '暂无描述'}
                  </Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    创建者ID: {session.created_by}
                  </Text>
                </Space>
              }
            />
          </List.Item>
        )}
      />

      <Modal
        title="创建协同会话"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        onOk={() => createForm.submit()}
        okText="创建"
        cancelText="取消"
      >
        <Form
          form={createForm}
          layout="vertical"
          initialValues={{ max_users: 10 }}
          onFinish={handleCreateSession}
        >
          <Form.Item
            name="session_name"
            label="会话名称"
            rules={[{ required: true, message: '请输入会话名称' }]}
          >
            <Input placeholder="如：项目A协同处理" />
          </Form.Item>
          <Form.Item name="description" label="会话描述">
            <Input.TextArea rows={3} placeholder="描述此会话的用途和目标..." />
          </Form.Item>
          <Form.Item name="max_users" label="最大参与人数">
            <Input type="number" min={2} max={50} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="会话参与者"
        open={usersModalOpen}
        onCancel={() => setUsersModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setUsersModalOpen(false)}>
            关闭
          </Button>
        ]}
      >
        <List
          dataSource={sessionUsers}
          locale={{ emptyText: '暂无参与者' }}
          renderItem={(userInfo) => (
            <List.Item>
              <List.Item.Meta
                avatar={<UserOutlined />}
                title={
                  <Space>
                    <Text>{userInfo.username}</Text>
                    <Tag>{userInfo.role}</Tag>
                    {userInfo.is_online && <Tag color="green">在线</Tag>}
                  </Space>
                }
                description={
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    加入时间: {new Date(userInfo.joined_at).toLocaleString()}
                  </Text>
                }
              />
            </List.Item>
          )}
        />
      </Modal>
    </Card>
  );
}
