import { Button, Card, Form, Input, Typography } from 'antd';
import { z } from 'zod';

const { Title, Paragraph } = Typography;

interface Props {
  loading: boolean;
  onSubmit: (values: { username: string; password: string }) => Promise<void>;
}

const schema = z.object({
  username: z.string().min(3, '用户名至少 3 位'),
  password: z.string().min(6, '密码至少 6 位')
});

export function LoginPage({ loading, onSubmit }: Props): JSX.Element {
  const [form] = Form.useForm<{ username: string; password: string }>();

  const handleFinish = async (values: { username: string; password: string }): Promise<void> => {
    schema.parse(values);
    await onSubmit(values);
  };

  return (
    <div className="login-page">
      <Card className="login-card" bordered={false}>
        <Title level={3} style={{ marginBottom: 8 }}>
          三维激光点云处理平台
        </Title>
        <Paragraph type="secondary" style={{ marginBottom: 24 }}>
          支持点云上传、处理、统计分析与审计追踪
        </Paragraph>

        <Form form={form} layout="vertical" onFinish={handleFinish}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input placeholder="请输入用户名" size="large" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password placeholder="请输入密码" size="large" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" block size="large" loading={loading}>
              登录系统
            </Button>
          </Form.Item>
        </Form>

        <Paragraph style={{ marginTop: 16, marginBottom: 0 }} type="secondary">
          默认账号：admin / 123456
        </Paragraph>
      </Card>
    </div>
  );
}
