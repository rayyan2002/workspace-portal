import { Component } from 'react'
import type { ReactNode, ErrorInfo } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import '../styles/error-boundary.css'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = {
      hasError: false,
      error: null
    }
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Render-phase error caught by ErrorBoundary:', error, errorInfo)
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary-container">
          <AlertTriangle size={48} className="error-boundary-icon" />
          <h2 className="error-boundary-heading">Something went wrong</h2>
          <p className="error-boundary-text">An unexpected error occurred while loading this page.</p>
          
          {import.meta.env.DEV && this.state.error && (
            <div className="error-boundary-box">
              <p className="error-boundary-dev-title">Developer Details:</p>
              <code>{this.state.error.message}</code>
            </div>
          )}
          
          <button onClick={this.handleReset} className="error-boundary-button">
            <RefreshCw size={16} />
            Try Again
          </button>
        </div>
      )
    }

    return this.props.children
  }
}