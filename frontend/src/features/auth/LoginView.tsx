import { InteractionStatus } from '@azure/msal-browser'
import { useMsal } from '@azure/msal-react'
import { ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { loginRequest } from './authConfig'
import './auth.css'

export function LoginView() {
  const { instance, inProgress } = useMsal()
  const [error, setError] = useState<string | null>(null)
  const isSigningIn = inProgress !== InteractionStatus.None

  const signIn = async () => {
    setError(null)

    try {
      await instance.loginRedirect(loginRequest)
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : 'Sign-in failed.')
    }
  }

  return (
    <main className="auth-screen">
      <section className="auth-card" aria-labelledby="login-title">
        <div className="auth-brand-mark">S</div>
        <p className="auth-kicker">SSC / AGENT</p>
        <h1 id="login-title">Sign in to your agent workspace.</h1>
        <p className="auth-description">
          Use your Microsoft account to access the engineering workspace.
        </p>
        <button
          className="auth-sign-in"
          type="button"
          onClick={() => void signIn()}
          disabled={isSigningIn}
        >
          <ShieldCheck size={18} />
          {isSigningIn ? 'Signing in…' : 'Sign in with Microsoft'}
        </button>
        {error && <p className="auth-error" role="alert">{error}</p>}
        <p className="auth-note">Authentication is provided by Microsoft Entra ID.</p>
      </section>
    </main>
  )
}
