/**
 * AppErrorBoundary — top-level React error boundary (story-5-2).
 *
 * Catches uncaught render errors and shows a full-page fallback.
 */
import { Component, ErrorInfo, ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class AppErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[AppErrorBoundary]", error, info.componentStack);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    window.location.href = "/";
  };

  render() {
    if (this.state.hasError) {
      return (
        <div
          role="alert"
          className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center"
        >
          <h1 className="text-2xl font-bold text-destructive">
            Something went wrong
          </h1>
          <p className="max-w-md text-muted-foreground">
            An unexpected error occurred. Please refresh the page or contact
            support if the problem persists.
          </p>
          <button
            type="button"
            onClick={this.handleReset}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            Return to dashboard
          </button>
          {import.meta.env.DEV && this.state.error && (
            <pre className="mt-4 max-w-xl overflow-auto rounded-md bg-muted p-4 text-left text-xs text-muted-foreground">
              {this.state.error.message}
            </pre>
          )}
        </div>
      );
    }

    return this.props.children;
  }
}
