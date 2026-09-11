import { useMsal } from '@azure/msal-react'
import { ArrowRight, Check } from 'lucide-react'
import { useState } from 'react'
import { runTestAgent } from '../../api/diagnostics/diagnostics'
import './auth.css'

type LoggedInViewProps = {
  onContinue: () => void
}

export function LoggedInView({ onContinue }: LoggedInViewProps) {
  const { accounts, instance } = useMsal()
  const account = instance.getActiveAccount() ?? accounts[0]
  const displayName = account?.name ?? account?.username ?? 'Microsoft account'
  const [testRunning, setTestRunning] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; text: string } | null>(null)

  const runConnectionTest = async () => {
    setTestRunning(true)
    setTestResult(null)

    try {
      const response = await runTestAgent()
      if (response.status !== 200) {
        throw new Error('The test agent request was rejected.')
      }
      setTestResult({ success: true, text: response.data.agentResponse })
    } catch (error) {
      setTestResult({
        success: false,
        text: error instanceof Error ? error.message : 'The test agent could not be reached.',
      })
    } finally {
      setTestRunning(false)
    }
  }

  return (
    <main className="auth-screen">
      <section className="auth-card logged-in-card" aria-labelledby="logged-in-title">
        <div className="auth-success-mark"><Check size={27} strokeWidth={2.5} /></div>
        <p className="auth-kicker">SSC / AGENT</p>
        <p className="auth-success-label">Authentication successful</p>
        <h1 id="logged-in-title">You are signed in.</h1>
        <p className="auth-description">Welcome, {displayName}.</p>
        <div className="auth-account-details">
          <span>Signed-in account</span>
          <strong>{account?.username ?? 'Account resolved by Microsoft Entra ID'}</strong>
        </div>
        <button
          className="auth-test-button"
          type="button"
          onClick={() => void runConnectionTest()}
          disabled={testRunning}
        >
          {testRunning ? 'Testing backend and agent…' : 'Test backend connection'}
        </button>
        {testResult && (
          <p className={`auth-test-result ${testResult.success ? 'success' : 'failure'}`} role="status">
            {testResult.text}
          </p>
        )}
        <button className="auth-sign-in" type="button" onClick={onContinue}>
          Continue to workspace <ArrowRight size={17} />
        </button>
        <p className="auth-note">Your Microsoft Entra ID session is active.</p>
      </section>
    </main>
  )
}
