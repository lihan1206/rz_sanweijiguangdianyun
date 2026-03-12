import {
  Alert,
  App,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Divider,
  Drawer,
  Form,
  Input,
  Layout,
  Menu,
  Modal,
  Row,
  Select,
  Skeleton,
  Space,
  Spin,
  Statistic,
  Switch,
  Table,
  Tag,
  Typography,
  Upload
} from 'antd';
import {
  DatabaseOutlined,
  DeleteOutlined,
  ExclamationCircleFilled,
  EyeOutlined,
  FileTextOutlined,
  LogoutOutlined,
  PlusOutlined,
  ReloadOutlined,
  RollbackOutlined,
  TeamOutlined,
  ToolOutlined,
  UploadOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import type { UploadFile } from 'antd/es/upload/interface';
import { useEffect, useMemo, useState } from 'react';
import { z } from 'zod';

import { PointCloudViewer } from '../components/PointCloudViewer';
import { api } from '../services/api';
import type {
  AuditLog,
  PointCloud,
  PointCloudStats,
  PointSample,
  ProcessingTask,
  TaskType,
  User
} from '../types';

const { Sider, Content } = Layout;
const { Title, Text } = Typography;

interface Props {
  user: User;
  onLogout: () => void;
}

const uploadSchema = z.object({
  name: z.string().min(2, '点云名称至少 2 个字'),
  file: z.any()
});

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function statusTag(status: ProcessingTask['status']): JSX.Element {
  const map: Record<ProcessingTask['status'], { color: string; text: string }> = {
    pending: { color: 'gold', text: '排队中' },
    running: { color: 'processing', text: '处理中' },
    success: { color: 'success', text: '已完成' },
    failed: { color: 'error', text: '失败' }
  };
  return <Tag color={map[status].color}>{map[status].text}</Tag>;
}

function roleLabel(role: User['role']): string {
  const map: Record<User['role'], string> = {
    admin: '管理员',
    engineer: '工程师',
    viewer: '查看员'
  };
  return map[role];
}

export function DashboardPage({ user, onLogout }: Props): JSX.Element {
  const { message } = App.useApp();
  const [pointclouds, setPointclouds] = useState<PointCloud[]>([]);
  const [tasks, setTasks] = useState<ProcessingTask[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [logs, setLogs] = useState<AuditLog[]>([]);

  const [loadingPointclouds, setLoadingPointclouds] = useState(false);
  const [loadingTasks, setLoadingTasks] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [creatingTask, setCreatingTask] = useState(false);

  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisPointcloud, setAnalysisPointcloud] = useState<PointCloud | null>(null);
  const [stats, setStats] = useState<PointCloudStats | null>(null);
  const [sample, setSample] = useState<PointSample | null>(null);
  const [activeMenuKey, setActiveMenuKey] = useState('pointcloud');

  const [uploadForm] = Form.useForm();
  const [taskForm] = Form.useForm();

  const isAdmin = user.role === 'admin';
  const canProcess = user.role === 'admin' || user.role === 'engineer';

  const pointcloudOptions = useMemo(
    () => pointclouds.filter((item) => !item.is_deleted).map((item) => ({ label: `${item.name} (ID:${item.id})`, value: item.id })),
    [pointclouds]
  );

  const loadPointclouds = async (): Promise<void> => {
    setLoadingPointclouds(true);
    try {
      const { data } = await api.get<PointCloud[]>('/pointclouds', { params: { include_deleted: includeDeleted } });
      setPointclouds(data);
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载点云数据失败');
    } finally {
      setLoadingPointclouds(false);
    }
  };

  const loadTasks = async (): Promise<void> => {
    setLoadingTasks(true);
    try {
      const { data } = await api.get<ProcessingTask[]>('/tasks');
      setTasks(data);
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载任务失败');
    } finally {
      setLoadingTasks(false);
    }
  };

  const loadUsers = async (): Promise<void> => {
    if (!isAdmin) return;
    try {
      const { data } = await api.get<User[]>('/users');
      setUsers(data);
    } catch {
      setUsers([]);
    }
  };

  const loadLogs = async (): Promise<void> => {
    if (!isAdmin) return;
    try {
      const { data } = await api.get<AuditLog[]>('/audit-logs');
      setLogs(data);
    } catch {
      setLogs([]);
    }
  };

  const refreshAll = async (): Promise<void> => {
    await Promise.all([loadPointclouds(), loadTasks(), loadUsers(), loadLogs()]);
  };

  useEffect(() => {
    void refreshAll();
  }, [includeDeleted]);

  const handleUpload = async (): Promise<void> => {
    const values = await uploadForm.validateFields();
    uploadSchema.parse(values);

    const selectedFile = (values.file?.[0] as UploadFile | undefined)?.originFileObj;
    if (!selectedFile) {
      message.error('请选择点云文件');
      return;
    }

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('name', values.name);
      if (values.group_name) formData.append('group_name', values.group_name);
      if (values.tags) formData.append('tags', values.tags);
      if (values.capture_time) formData.append('capture_time', dayjs(values.capture_time).toISOString());
      if (values.sensor_model) formData.append('sensor_model', values.sensor_model);
      if (values.coordinate_system) formData.append('coordinate_system', values.coordinate_system);

      await api.post('/pointclouds/upload', formData);
      message.success('点云上传成功');
      setUploadOpen(false);
      uploadForm.resetFields();
      await loadPointclouds();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '上传失败');
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = (record: PointCloud): void => {
    Modal.confirm({
      title: '确认删除点云数据',
      icon: <ExclamationCircleFilled style={{ color: '#ff4d4f' }} />,
      centered: true,
      okText: '确认删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      content: (
        <div style={{ marginTop: 8 }}>
          <Card size="small" style={{ borderColor: '#ffd6d6', background: '#fff2f0' }}>
            <Text strong style={{ color: '#cf1322' }}>
              删除后将进入回收站，可手动恢复。
            </Text>
            <br />
            <Text type="secondary">点云名称：{record.name}</Text>
            <br />
            <Text type="secondary">文件：{record.original_filename}</Text>
          </Card>
        </div>
      ),
      onOk: async () => {
        try {
          await api.delete(`/pointclouds/${record.id}`);
          message.success('删除成功，已移入回收站');
          await loadPointclouds();
        } catch (error: any) {
          message.error(error.response?.data?.detail || '删除失败');
        }
      }
    });
  };

  const handleRestore = async (record: PointCloud): Promise<void> => {
    try {
      await api.post(`/pointclouds/${record.id}/restore`);
      message.success('恢复成功');
      await loadPointclouds();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '恢复失败');
    }
  };

  const openAnalysis = async (record: PointCloud): Promise<void> => {
    setAnalysisPointcloud(record);
    setAnalysisOpen(true);
    setAnalysisLoading(true);
    try {
      const [statsResp, sampleResp] = await Promise.all([
        api.get<PointCloudStats>(`/pointclouds/${record.id}/stats`),
        api.get<PointSample>(`/pointclouds/${record.id}/sample`, { params: { limit: 3000 } })
      ]);
      setStats(statsResp.data);
      setSample(sampleResp.data);
    } catch (error: any) {
      setStats(null);
      setSample(null);
      message.error(error.response?.data?.detail || '分析失败，该格式可能暂不支持可视化');
    } finally {
      setAnalysisLoading(false);
    }
  };

  const handleCreateTask = async (): Promise<void> => {
    const values = await taskForm.validateFields();
    setCreatingTask(true);
    try {
      const taskType = values.task_type as TaskType;
      const params: Record<string, number> = {};

      if (taskType === 'downsample') {
        params.ratio = Number(values.ratio);
      }
      if (taskType === 'denoise') {
        params.zscore = Number(values.zscore);
      }
      if (taskType === 'clip_z') {
        params.min_z = Number(values.min_z);
        params.max_z = Number(values.max_z);
      }

      await api.post('/tasks', {
        pointcloud_id: values.pointcloud_id,
        task_type: taskType,
        output_format: values.output_format,
        parameters: params
      });

      message.success('任务已提交，系统正在后台处理');
      taskForm.resetFields();
      await loadTasks();
      await loadPointclouds();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '任务提交失败');
    } finally {
      setCreatingTask(false);
    }
  };

  const pointcloudColumns = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 70
    },
    {
      title: '点云名称',
      dataIndex: 'name',
      render: (value: string, row: PointCloud) => (
        <Space direction="vertical" size={0}>
          <Text strong>{value}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {row.original_filename}
          </Text>
        </Space>
      )
    },
    {
      title: '格式',
      dataIndex: 'file_format',
      width: 90,
      render: (value: string) => <Tag color="blue">{value.toUpperCase()}</Tag>
    },
    {
      title: '点数',
      dataIndex: 'points_count',
      width: 120,
      render: (value: number | null) => (value ?? '未知')
    },
    {
      title: '分组/标签',
      width: 210,
      render: (_: unknown, row: PointCloud) => (
        <Space direction="vertical" size={2}>
          <Text>{row.group_name || '未分组'}</Text>
          <Space size={4} wrap>
            {(row.tags || []).map((tag) => (
              <Tag key={tag}>{tag}</Tag>
            ))}
          </Space>
        </Space>
      )
    },
    {
      title: '文件大小',
      dataIndex: 'file_size',
      width: 120,
      render: (value: number) => formatBytes(value)
    },
    {
      title: '状态',
      dataIndex: 'is_deleted',
      width: 110,
      render: (value: boolean) => (value ? <Tag color="red">已删除</Tag> : <Tag color="green">正常</Tag>)
    },
    {
      title: '操作',
      width: 240,
      render: (_: unknown, record: PointCloud) => (
        <Space wrap>
          <Button icon={<EyeOutlined />} onClick={() => void openAnalysis(record)}>
            分析
          </Button>
          {record.is_deleted ? (
            <Button icon={<RollbackOutlined />} onClick={() => void handleRestore(record)}>
              恢复
            </Button>
          ) : (
            canProcess && (
              <Button danger icon={<DeleteOutlined />} onClick={() => handleDelete(record)}>
                删除
              </Button>
            )
          )}
        </Space>
      )
    }
  ];

  const taskColumns = [
    { title: '任务ID', dataIndex: 'id', width: 90 },
    { title: '源点云ID', dataIndex: 'pointcloud_id', width: 110 },
    {
      title: '处理类型',
      dataIndex: 'task_type',
      width: 120,
      render: (value: string) => {
        const map: Record<string, string> = {
          downsample: '降采样',
          denoise: '去噪',
          clip_z: '高度裁剪',
          format_convert: '格式转换'
        };
        return map[value] || value;
      }
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (value: ProcessingTask['status']) => statusTag(value)
    },
    { title: '输出格式', dataIndex: 'output_format', width: 100 },
    {
      title: '结果点云ID',
      dataIndex: 'result_pointcloud_id',
      width: 130,
      render: (value: number | null) => value || '-'
    },
    {
      title: '失败原因',
      dataIndex: 'error_message',
      ellipsis: true,
      render: (value: string | null) => value || '-'
    }
  ];

  const taskType = Form.useWatch('task_type', taskForm);

  const tabItems: { key: string; label: string; children: JSX.Element }[] = [
    {
      key: 'pointcloud',
      label: '点云数据管理',
      children: (
        <Card bordered={false}>
          <Space style={{ marginBottom: 16 }} wrap>
            {canProcess && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setUploadOpen(true)}>
                上传点云
              </Button>
            )}
            <Space>
              <Text>显示已删除数据</Text>
              <Switch checked={includeDeleted} onChange={setIncludeDeleted} />
            </Space>
          </Space>
          <Table
            rowKey="id"
            loading={loadingPointclouds}
            columns={pointcloudColumns}
            dataSource={pointclouds}
            scroll={{ x: 1200 }}
            pagination={{ pageSize: 8 }}
          />
        </Card>
      )
    },
    {
      key: 'tasks',
      label: '点云处理流程',
      children: (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          {canProcess ? (
            <Card title="创建处理任务" bordered={false}>
              <Form
                form={taskForm}
                layout="vertical"
                initialValues={{ task_type: 'downsample', output_format: 'xyz', ratio: 0.5, zscore: 2 }}
              >
                <Row gutter={16}>
                  <Col xs={24} md={8}>
                    <Form.Item name="pointcloud_id" label="选择源点云" rules={[{ required: true, message: '请选择点云' }]}>
                      <Select options={pointcloudOptions} placeholder="请选择点云" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={8}>
                    <Form.Item name="task_type" label="处理算法" rules={[{ required: true, message: '请选择处理算法' }]}>
                      <Select
                        options={[
                          { label: '降采样', value: 'downsample' },
                          { label: '去噪', value: 'denoise' },
                          { label: '高度裁剪', value: 'clip_z' },
                          { label: '格式转换', value: 'format_convert' }
                        ]}
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={8}>
                    <Form.Item name="output_format" label="输出格式" rules={[{ required: true, message: '请选择输出格式' }]}>
                      <Select
                        options={[
                          { label: 'XYZ', value: 'xyz' },
                          { label: 'CSV', value: 'csv' },
                          { label: 'PLY', value: 'ply' }
                        ]}
                      />
                    </Form.Item>
                  </Col>
                </Row>

                {taskType === 'downsample' && (
                  <Form.Item
                    name="ratio"
                    label="降采样比例(0.01-1)"
                    rules={[{ required: true, message: '请输入比例' }]}
                  >
                    <Input type="number" min={0.01} max={1} step={0.01} />
                  </Form.Item>
                )}

                {taskType === 'denoise' && (
                  <Form.Item name="zscore" label="离群阈值(Z-Score)" rules={[{ required: true, message: '请输入阈值' }]}>
                    <Input type="number" min={1} max={6} step={0.1} />
                  </Form.Item>
                )}

                {taskType === 'clip_z' && (
                  <Row gutter={16}>
                    <Col xs={24} md={12}>
                      <Form.Item name="min_z" label="最小高度" rules={[{ required: true, message: '请输入最小高度' }]}>
                        <Input type="number" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} md={12}>
                      <Form.Item name="max_z" label="最大高度" rules={[{ required: true, message: '请输入最大高度' }]}>
                        <Input type="number" />
                      </Form.Item>
                    </Col>
                  </Row>
                )}

                <Button type="primary" onClick={() => void handleCreateTask()} loading={creatingTask}>
                  提交处理任务
                </Button>
              </Form>
            </Card>
          ) : (
            <Alert type="info" message="当前角色仅支持查看任务，无法创建处理任务。" showIcon />
          )}

          <Card title="任务历史" bordered={false}>
            <Table
              rowKey="id"
              loading={loadingTasks}
              columns={taskColumns}
              dataSource={tasks}
              scroll={{ x: 1100 }}
              pagination={{ pageSize: 8 }}
            />
          </Card>
        </Space>
      )
    }
  ];

  if (isAdmin) {
    tabItems.push({
      key: 'users',
      label: '用户权限管理',
      children: (
        <Card bordered={false}>
          <Table
            rowKey="id"
            dataSource={users}
            pagination={false}
            columns={[
              { title: '用户ID', dataIndex: 'id', width: 90 },
              { title: '用户名', dataIndex: 'username' },
              {
                title: '角色',
                dataIndex: 'role',
                render: (value: User['role']) => <Tag color="purple">{roleLabel(value)}</Tag>
              },
              {
                title: '状态',
                dataIndex: 'is_active',
                render: (value: boolean) => (value ? <Tag color="green">启用</Tag> : <Tag color="red">禁用</Tag>)
              }
            ]}
          />
        </Card>
      )
    });

    tabItems.push({
      key: 'audit',
      label: '操作审计日志',
      children: (
        <Card bordered={false}>
          <Table
            rowKey="id"
            dataSource={logs}
            pagination={{ pageSize: 10 }}
            columns={[
              { title: '日志ID', dataIndex: 'id', width: 90 },
              { title: '用户ID', dataIndex: 'user_id', width: 90 },
              { title: '动作', dataIndex: 'action', width: 180 },
              { title: '目标类型', dataIndex: 'target_type', width: 120 },
              { title: '目标ID', dataIndex: 'target_id', width: 100 },
              {
                title: '时间',
                dataIndex: 'created_at',
                render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm:ss')
              }
            ]}
          />
        </Card>
      )
    });
  }

  const menuItems = tabItems.map((item) => {
    const iconMap: Record<string, JSX.Element> = {
      pointcloud: <DatabaseOutlined />,
      tasks: <ToolOutlined />,
      users: <TeamOutlined />,
      audit: <FileTextOutlined />
    };
    return {
      key: item.key,
      icon: iconMap[item.key] || <DatabaseOutlined />,
      label: item.label
    };
  });

  const currentPanel =
    tabItems.find((item) => item.key === activeMenuKey)?.children || tabItems[0].children;

  return (
    <Layout className="dashboard-layout">
      <Sider breakpoint="lg" collapsedWidth="0" width={248} className="left-nav">
        <div className="left-nav-head">
          <Title level={4} style={{ margin: 0, color: '#fff' }}>
            三维激光点云处理平台
          </Title>
            </div>

        <Divider style={{ margin: '12px 0', borderColor: 'rgba(255,255,255,0.12)' }} />

        <div className="left-nav-user">
          <Text style={{ color: '#e9f3ff' }}>用户：{user.username}</Text>
          <Tag color="blue" style={{ marginInlineEnd: 0 }}>
            {roleLabel(user.role)}
          </Tag>
        </div>

        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[activeMenuKey]}
          items={menuItems}
          onClick={({ key }) => setActiveMenuKey(key)}
          style={{ marginTop: 12, background: 'transparent' }}
        />

        <div className="left-nav-actions">
          <Button icon={<ReloadOutlined />} onClick={() => void refreshAll()} block>
            刷新数据
          </Button>
          <Button icon={<LogoutOutlined />} danger onClick={onLogout} block>
            退出登录
          </Button>
        </div>
      </Sider>

      <Layout>
        <Content style={{ padding: 20 }}>{currentPanel}</Content>
      </Layout>

      <Modal
        title="上传点云文件"
        open={uploadOpen}
        onCancel={() => setUploadOpen(false)}
        onOk={() => void handleUpload()}
        okText="确认上传"
        cancelText="取消"
        confirmLoading={uploading}
        width={680}
      >
        <Form form={uploadForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="name" label="点云名称" rules={[{ required: true, message: '请输入点云名称' }]}>
                <Input placeholder="如：园区一期扫描数据" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="group_name" label="分组">
                <Input placeholder="如：项目A / 区域1" />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="tags" label="标签(英文逗号分隔)">
                <Input placeholder="地形,建筑,道路" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="capture_time" label="采集时间">
                <DatePicker showTime style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="sensor_model" label="传感器型号">
                <Input placeholder="如：Velodyne VLP-16" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="coordinate_system" label="坐标系">
                <Input placeholder="如：WGS84 / EPSG:4490" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            name="file"
            label="点云文件"
            valuePropName="fileList"
            getValueFromEvent={(event) => event?.fileList}
            rules={[{ required: true, message: '请选择点云文件' }]}
          >
            <Upload
              beforeUpload={() => false}
              maxCount={1}
              accept=".las,.laz,.ply,.xyz,.e57,.csv"
              listType="text"
            >
              <Button icon={<UploadOutlined />}>选择文件（支持 las/laz/ply/xyz/e57/csv）</Button>
            </Upload>
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={analysisPointcloud ? `点云分析 - ${analysisPointcloud.name}` : '点云分析'}
        open={analysisOpen}
        onClose={() => setAnalysisOpen(false)}
        width={980}
      >
        {analysisLoading ? (
          <Skeleton active paragraph={{ rows: 8 }} />
        ) : !stats || !sample ? (
          <Alert type="warning" showIcon message="当前文件格式暂不支持统计或可视化" />
        ) : (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Card bordered={false}>
              <Row gutter={16}>
                <Col xs={12} md={6}>
                  <Statistic title="总点数" value={stats.total_points} />
                </Col>
                <Col xs={12} md={6}>
                  <Statistic title="密度估算" value={stats.density_estimate} precision={2} />
                </Col>
                <Col xs={12} md={6}>
                  <Statistic title="X范围" value={`${stats.x_range[0].toFixed(2)} ~ ${stats.x_range[1].toFixed(2)}`} />
                </Col>
                <Col xs={12} md={6}>
                  <Statistic title="Z范围" value={`${stats.z_range[0].toFixed(2)} ~ ${stats.z_range[1].toFixed(2)}`} />
                </Col>
              </Row>
              <Descriptions size="small" column={1} style={{ marginTop: 16 }}>
                <Descriptions.Item label="Y范围">
                  {stats.y_range[0].toFixed(2)} ~ {stats.y_range[1].toFixed(2)}
                </Descriptions.Item>
              </Descriptions>
            </Card>

            <Card title="3D 点云预览（采样）" bordered={false}>
              {sample.points.length === 0 ? <Spin /> : <PointCloudViewer points={sample.points} />}
            </Card>
          </Space>
        )}
      </Drawer>
    </Layout>
  );
}
