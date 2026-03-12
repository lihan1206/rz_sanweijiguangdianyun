import { App as AntApp, ConfigProvider, message } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { useEffect, useState } from 'react';

import { ErrorBoundary } from './components/ErrorBoundary';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { api } from './services/api';
import { clearAuth, getToken, getStoredUser, setStoredUser, setToken } from './services/auth';
import type { User } from './types';

function AppShell(): JSX.Element {
  const [user, setUser] = useState<User | null>(getStoredUser());
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const init = async (): Promise<void> => {
      const token = getToken();
      if (!token) {
        setChecking(false);
        return;
      }

      try {
        const { data } = await api.get<User>('/auth/me');
        setUser(data);
        setStoredUser(data);
      } catch {
        clearAuth();
        setUser(null);
      } finally {
        setChecking(false);
      }
    };

    void init();
  }, []);

  const handleLogin = async (values: { username: string; password: string }): Promise<void> => {
    setLoading(true);
    try {
      const { data } = await api.post<{ access_token: string }>('/auth/login', values);
      setToken(data.access_token);

      const profile = await api.get<User>('/auth/me');
      setUser(profile.data);
      setStoredUser(profile.data);
      message.success('登录成功');
    } catch (error: any) {
      message.error(error.response?.data?.detail || '登录失败');
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = (): void => {
    clearAuth();
    setUser(null);
  };

  if (checking) {
    return <div style={{ padding: 32 }}>正在校验登录状态...</div>;
  }

  if (!user) {
    return <LoginPage loading={loading} onSubmit={handleLogin} />;
  }

  return <DashboardPage user={user} onLogout={handleLogout} />;
}

export default function App(): JSX.Element {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#0d6efd',
          borderRadius: 10
        }
      }}
    >
      <AntApp>
        <ErrorBoundary>
          <AppShell />
        </ErrorBoundary>
      </AntApp>
    </ConfigProvider>
  );
}
