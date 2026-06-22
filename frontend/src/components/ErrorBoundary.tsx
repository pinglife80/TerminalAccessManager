import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertCircle, RefreshCw, Home } from 'lucide-react';
import { logger } from '../lib/logger';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      error,
      errorInfo: null,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    logger.error('ErrorBoundary', `Uncaught error: ${error.message}`, {
      stack: error.stack,
      componentStack: errorInfo.componentStack,
    });
    this.setState({ errorInfo });
  }

  handleRefresh = (): void => {
    window.location.reload();
  };

  handleGoHome = (): void => {
    window.location.href = '/';
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-background flex items-center justify-center p-4">
          <div className="bg-card rounded-xl shadow-lg p-8 max-w-md w-full text-center">
            <div className="w-20 h-20 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-6">
              <AlertCircle className="h-10 w-10 text-red-600" />
            </div>

            <h2 className="text-2xl font-bold text-foreground mb-4">
              Something went wrong
            </h2>

            <p className="text-muted-foreground mb-6">
              We're sorry, but an unexpected error occurred. Please try again later.
            </p>

            {this.state.error && (
              <div className="bg-muted rounded-lg p-4 mb-6 text-left">
                <p className="text-sm text-muted-foreground font-medium mb-1">Error:</p>
                <p className="text-sm text-muted-foreground font-mono break-all">
                  {this.state.error.message}
                </p>
              </div>
            )}

            <div className="flex flex-col gap-3">
              <button
                onClick={this.handleRefresh}
                className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                <RefreshCw className="h-5 w-5" />
                Refresh Page
              </button>

              <button
                onClick={this.handleGoHome}
                className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-muted text-foreground rounded-lg hover:bg-muted/80 transition-colors"
              >
                <Home className="h-5 w-5" />
                Go to Home
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
