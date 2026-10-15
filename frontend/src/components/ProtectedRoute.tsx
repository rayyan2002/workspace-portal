import { Navigate, Outlet } from 'react-router'
import { useAuth } from '../context/AuthContext'

function ProtectedRoute() {
  const { user, loading } = useAuth()

  if (loading) {
    return <div className="app-loading">Restoring session details...</div>
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}

export default ProtectedRoute