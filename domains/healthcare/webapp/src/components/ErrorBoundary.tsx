import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Short label for the failed region, shown to the user. */
  label: string;
}

interface State {
  error: Error | null;
}

/** Contains render failures so one malformed result cannot blank the whole console. */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // Log only the error shape; never the clinical payload being rendered.
    console.error(`[${this.props.label}] render failed:`, error.name, error.message, info.componentStack);
  }

  override render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div className="alert alert-error" role="alert">
        <strong>{this.props.label} could not be displayed.</strong> {this.state.error.message}{" "}
        <button type="button" className="link" onClick={() => this.setState({ error: null })}>
          Try again
        </button>
      </div>
    );
  }
}
