import React from 'react';
import { Alert, Button } from 'antd';

interface Props {
  children: React.ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error): void {
    // 前端异常仅做边界兜底，不影响页面其它功能。
    console.error('页面渲染异常:', error);
  }

  handleRefresh = (): void => {
    window.location.reload();
  };

  render(): React.ReactNode {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 24 }}>
          <Alert
            type="error"
            showIcon
            message="页面发生异常"
            description="已为你拦截错误，你可以刷新页面后继续操作。"
            action={<Button onClick={this.handleRefresh}>刷新页面</Button>}
          />
        </div>
      );
    }

    return this.props.children;
  }
}
