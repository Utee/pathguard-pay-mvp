import React, { useEffect, useState } from 'react';
import {
  ShieldCheck,
  ShieldX,
  CheckCircle2,
  Clock3,
  ArrowRight,
  Loader2,
  ShieldAlert,
  History,
  PartyPopper,
  XCircle,
  Settings2,
  Save,
  Activity,
  AlertTriangle,
  TrendingUp,
  CircleDollarSign,
  Bell,
  Link2,
  Unlink,
} from 'lucide-react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

function apiFetch(input, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = localStorage.getItem('pathguard_access_token');
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(input, { ...options, headers });
}

const STATUS_LABELS = {
  ALLOW: 'Approved',
  BLOCK: 'Blocked',
  REVIEW_PENDING: 'Awaiting review',
  REVIEW_APPROVED: 'Review approved',
  REVIEW_REJECTED: 'Review rejected',
  PAYPAL_PENDING_APPROVAL: 'Awaiting PayPal approval',
  PAYPAL_PENDING_CAPTURE: 'Capturing payment',
  COMPLETED: 'Completed',
};

function statusMeta(status) {
  if (status === 'BLOCK' || status === 'REVIEW_REJECTED') {
    return { tone: 'danger', label: STATUS_LABELS[status] || status, icon: <ShieldX /> };
  }
  if (status === 'ALLOW' || status === 'COMPLETED') {
    return { tone: 'success', label: STATUS_LABELS[status] || status, icon: <CheckCircle2 /> };
  }
  if (status === 'PAYPAL_PENDING_APPROVAL' || status === 'PAYPAL_PENDING_CAPTURE') {
    return { tone: 'info', label: STATUS_LABELS[status] || status, icon: <Loader2 className="spin" /> };
  }
  return { tone: 'warning', label: STATUS_LABELS[status] || status, icon: <Clock3 /> };
}

function App() {
  const [token, setToken] = useState(() => localStorage.getItem('pathguard_access_token'));
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authMode, setAuthMode] = useState('login');
  const [authEmail, setAuthEmail] = useState('');
  const [authName, setAuthName] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState('');
  const [activeTab, setActiveTab] = useState('overview');
  const [instruction, setInstruction] = useState('');
  const [payment, setPayment] = useState(null);
  const [history, setHistory] = useState([]);
  const [reviewQueue, setReviewQueue] = useState([]);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [payLoading, setPayLoading] = useState(false);
  const [error, setError] = useState('');
  const [paypalResult, setPaypalResult] = useState(null);
  const [intelligenceOverview, setIntelligenceOverview] = useState(null);
  const [incidents, setIncidents] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [intelligenceSummary, setIntelligenceSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState('');
  const [limitDraft, setLimitDraft] = useState({
    daily_limit: 1000,
    weekly_limit: 10000,
    monthly_limit: 10000,
    per_transaction_limit: null,
    timezone: 'Africa/Lagos',
  });
  const [limitSummary, setLimitSummary] = useState(null);
  const [limitsSaving, setLimitsSaving] = useState(false);
  const [limitsInitialized, setLimitsInitialized] = useState(false);
  const [limitsError, setLimitsError] = useState('');
  const [limitsSaved, setLimitsSaved] = useState('');
  const [paypalConnection, setPaypalConnection] = useState({ connected: false, status: 'not_connected' });
  const [paypalConnectionBusy, setPaypalConnectionBusy] = useState(false);
  const [paypalConnectionNotice, setPaypalConnectionNotice] = useState('');
  const [paypalConnectionError, setPaypalConnectionError] = useState('');

  async function load(account = user) {
    try {
      const r = await apiFetch(`${API}/api/payments`);
      if (r.ok) setHistory(await r.json());

      if (account && ['reviewer', 'admin'].includes(account.role)) {
        const reviews = await apiFetch(`${API}/api/reviews`);
        if (reviews.ok) setReviewQueue(await reviews.json());
      } else {
        setReviewQueue([]);
      }

      const paypalConnectionResponse = await apiFetch(`${API}/api/paypal/connection`);
      if (paypalConnectionResponse.ok) setPaypalConnection(await paypalConnectionResponse.json());

      const configuredLimits = await apiFetch(`${API}/api/limits/settings`);
      if (configuredLimits.ok && !limitsInitialized) {
        const d = await configuredLimits.json();
        setLimitDraft({
          daily_limit: d.daily_limit,
          weekly_limit: d.weekly_limit,
          monthly_limit: d.monthly_limit,
          per_transaction_limit: d.per_transaction_limit,
          timezone: d.timezone,
        });
        setLimitsInitialized(true);
      }

      const usage = await apiFetch(`${API}/api/limits/summary`);
      if (usage.ok) setLimitSummary(await usage.json());

      const overview = await apiFetch(`${API}/api/intelligence/overview`);
      if (overview.ok) setIntelligenceOverview(await overview.json());

      const incidentResponse = await apiFetch(`${API}/api/intelligence/incidents`);
      if (incidentResponse.ok) {
        const data = await incidentResponse.json();
        setIncidents(data.incidents || []);
      }

      const notificationResponse = await apiFetch(`${API}/api/intelligence/notifications?limit=15`);
      if (notificationResponse.ok) {
        const data = await notificationResponse.json();
        setNotifications(data.notifications || []);
      }
    } catch {
      // Keep the dashboard usable if history is temporarily unavailable.
    }
  }

  async function restorePayment(paymentId) {
    if (!paymentId) return;

    try {
      const r = await apiFetch(`${API}/api/payments/${paymentId}`);
      const d = await r.json();

      if (r.ok && d?.id) {
        setPayment({
          payment_id: d.id,
          intent: {
            recipient_name: d.recipient,
            amount: Number(d.amount),
            currency: d.currency,
            purpose: d.purpose,
          },
          risk: d.risk,
          paypal: d.paypal,
          status: d.status,
        });
      }
    } catch {
      // The result banner remains useful even if payment detail temporarily fails.
    }
  }

  useEffect(() => {
    let active = true;
    async function initialize() {
      if (!token) {
        setUser(null);
        setAuthLoading(false);
        return;
      }

      setAuthLoading(true);
      try {
        const accountResponse = await apiFetch(`${API}/api/auth/me`);
        if (!active) return;
        if (!accountResponse.ok) {
          localStorage.removeItem('pathguard_access_token');
          setToken(null);
          setUser(null);
          setAuthLoading(false);
          return;
        }
        const account = await accountResponse.json();
        if (!active) return;
        setUser(account);
        setAuthLoading(false);
        load(account);
      } catch {
        if (active) {
          setAuthLoading(false);
          setAuthError('Could not connect to PathGuard Pay. Check that the backend is running.');
        }
        return;
      }

    const q = new URLSearchParams(window.location.search);
    const paypalState = q.get('paypal');
    const paypalConnectState = q.get('paypal_connect');
    const paypalToken = q.get('token');
    const paymentId = q.get('payment_id');
    const orderId = q.get('order_id');
    const captureId = q.get('capture_id');
    const message = q.get('message');
    const approvalUrl = q.get('approval_url');

    if (paypalConnectState === 'connected') {
      setPaypalConnectionNotice('PayPal wallet connected. PathGuard can now use this saved Sandbox wallet after a payment passes its risk and spending-limit checks.');
      setPaypalConnectionError('');
    } else if (paypalConnectState === 'cancelled') {
      setPaypalConnectionNotice('PayPal wallet connection was cancelled. No new wallet was saved.');
      setPaypalConnectionError('');
    } else if (paypalConnectState === 'error') {
      setPaypalConnectionError('Could not connect PayPal. Confirm Vault is enabled in your Sandbox REST app and that the vault encryption key is configured.');
      setPaypalConnectionNotice('');
    }

    const savedPaymentId = localStorage.getItem('pathguard_paypal_payment_id');
    const effectivePaymentId = paymentId || savedPaymentId;

    async function syncReturnedPayment(token) {
      if (!token) return null;

      try {
        const r = await apiFetch(
          `${API}/api/payments/paypal/sync?token=${encodeURIComponent(token)}`,
          { method: 'POST' }
        );
        const d = await r.json();

        if (!r.ok) {
          throw new Error(d.detail || 'Could not synchronize PayPal payment');
        }

        if (d.status === 'PAYPAL_REAUTH_REQUIRED' && d.approval_url) {
          window.location.href = d.approval_url;
          return null;
        }

        return d;
      } catch (e) {
        setError(e.message || 'Could not synchronize PayPal payment');
        return null;
      }
    }

    async function restoreAfterPayPalReturn() {
      if (paypalState === 'reauth' && approvalUrl) {
        window.location.href = approvalUrl;
        return;
      }

      let synced = null;

      if (paypalToken) {
        synced = await syncReturnedPayment(paypalToken);
      } else if (effectivePaymentId) {
        const current = await apiFetch(`${API}/api/payments/${effectivePaymentId}`);
        if (current.ok) {
          const d = await current.json();
          const token = d?.paypal?.order_id;

          if (token && ['PAYPAL_PENDING_APPROVAL', 'PAYPAL_PENDING_CAPTURE'].includes(d.status)) {
            synced = await syncReturnedPayment(token);
          }
        }
      }

      const finalPaymentId = synced?.payment_id || effectivePaymentId;
      if (finalPaymentId) {
        await restorePayment(finalPaymentId);
      }

      if (synced?.status === 'COMPLETED') {
        setPaypalResult({
          state: 'completed',
          paymentId: synced.payment_id,
          orderId: synced.paypal_order_id,
          captureId: synced.capture_id,
        });
      } else if (paypalState) {
        setPaypalResult({
          state: paypalState,
          paymentId: finalPaymentId,
          orderId: orderId || synced?.paypal_order_id,
          captureId: captureId || synced?.capture_id,
          message,
        });
      }

      load(account);
      localStorage.removeItem('pathguard_paypal_payment_id');
    }

    restoreAfterPayPalReturn();

    window.history.replaceState({}, '', window.location.pathname);
    }

    initialize();
    return () => { active = false; };
  }, [token]);

  async function submitAuth(event) {
    event.preventDefault();
    setAuthBusy(true);
    setAuthError('');
    try {
      const endpoint = authMode === 'register' ? '/api/auth/register' : '/api/auth/login';
      const payload = authMode === 'register'
        ? { email: authEmail, display_name: authName, password: authPassword }
        : { email: authEmail, password: authPassword };
      const response = await fetch(`${API}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        const detail = typeof data.detail === 'string'
          ? data.detail
          : Array.isArray(data.detail)
            ? data.detail.map((item) => item.msg).join('; ')
            : 'Authentication failed.';
        throw new Error(detail);
      }
      localStorage.setItem('pathguard_access_token', data.access_token);
      setUser(data.user);
      setToken(data.access_token);
      setAuthPassword('');
      setAuthError('');
    } catch (error) {
      setAuthError(error.message || 'Authentication failed.');
    } finally {
      setAuthBusy(false);
    }
  }

  function signOut() {
    localStorage.removeItem('pathguard_access_token');
    localStorage.removeItem('pathguard_paypal_payment_id');
    setToken(null);
    setUser(null);
    setPayment(null);
    setHistory([]);
    setReviewQueue([]);
    setIntelligenceOverview(null);
    setIncidents([]);
    setNotifications([]);
    setIntelligenceSummary(null);
    setPaypalConnection({ connected: false, status: 'not_connected' });
    setPaypalConnectionNotice('');
    setPaypalConnectionError('');
    setSummaryError('');
    setLimitsInitialized(false);
    setLimitSummary(null);
  }

  async function decideReview(item, action) {
    setReviewLoading(true);
    setError('');

    try {
      const r = await apiFetch(`${API}/api/reviews/${item.id}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          reviewer: 'local-reviewer',
          note: action === 'approve'
            ? 'Approved after human review.'
            : 'Rejected after human review.',
        }),
      });

      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Could not update review');

      setReviewQueue((items) => items.filter((x) => x.id !== item.id));
      setHistory((items) =>
        items.map((x) => x.id === item.id ? { ...x, status: d.status } : x)
      );
      setPayment((current) =>
        current?.payment_id === item.id
          ? { ...current, status: d.status }
          : current
      );
    } catch (e) {
      setError(e.message || 'Could not update review');
    } finally {
      setReviewLoading(false);
      load();
    }
  }

  async function saveLimits() {
    setLimitsSaving(true);
    setLimitsError('');
    setLimitsSaved('');

    const fields = ['daily_limit', 'weekly_limit', 'monthly_limit', 'per_transaction_limit'];
    const payload = { ...limitDraft };
    for (const field of fields) {
      const value = payload[field];
      payload[field] = value === '' || value === null || value === undefined
        ? null
        : Number(value);
    }

    if (fields.every((field) => payload[field] === null)) {
      setLimitsError('Keep at least one spending limit enabled.');
      setLimitsSaving(false);
      return;
    }

    try {
      const r = await apiFetch(`${API}/api/limits/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const d = await r.json();
      if (!r.ok) {
        const detail = typeof d.detail === 'string'
          ? d.detail
          : Array.isArray(d.detail)
            ? d.detail.map((item) => item.msg).join('; ')
            : 'Could not save spending limits';
        throw new Error(detail);
      }

      setLimitDraft(d);
      setLimitsSaved('Spending limits saved. New and pending payments will be checked against these settings.');
      const summaryResponse = await apiFetch(`${API}/api/limits/summary`);
      if (summaryResponse.ok) setLimitSummary(await summaryResponse.json());
    } catch (e) {
      setLimitsError(e.message || 'Could not save spending limits');
    } finally {
      setLimitsSaving(false);
    }
  }

  async function connectPaypal() {
    setPaypalConnectionBusy(true);
    setPaypalConnectionError('');
    setPaypalConnectionNotice('');
    try {
      const response = await apiFetch(`${API}/api/paypal/connection/setup`, {
        method: 'POST',
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not start PayPal connection.');
      if (!data.approval_url) throw new Error('PayPal did not return a wallet approval URL.');
      window.location.href = data.approval_url;
    } catch (error) {
      setPaypalConnectionError(error.message || 'Could not connect PayPal.');
      setPaypalConnectionBusy(false);
    }
  }

  async function disconnectPaypal() {
    setPaypalConnectionBusy(true);
    setPaypalConnectionError('');
    setPaypalConnectionNotice('');
    try {
      const response = await apiFetch(`${API}/api/paypal/connection`, {
        method: 'DELETE',
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not disconnect PayPal.');
      setPaypalConnection(data);
      setPaypalConnectionNotice('PayPal wallet disconnected and its saved token was revoked.');
    } catch (error) {
      setPaypalConnectionError(error.message || 'Could not disconnect PayPal.');
    } finally {
      setPaypalConnectionBusy(false);
    }
  }

  async function generateSummary() {
    setSummaryLoading(true);
    setSummaryError('');
    try {
      const response = await apiFetch(`${API}/api/intelligence/summary`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not generate the intelligence summary.');
      setIntelligenceSummary(data);
    } catch (error) {
      setSummaryError(error.message || 'Could not generate the intelligence summary.');
    } finally {
      setSummaryLoading(false);
    }
  }

  async function analyze() {
    if (!instruction.trim()) return;

    setLoading(true);
    setError('');
    setPaypalResult(null);
    setPayment(null);

    try {
      const r = await apiFetch(`${API}/api/payments/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction }),
      });

      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Analysis failed');

      setPayment({
        ...d,
        status: d.risk?.decision === 'REVIEW'
          ? 'REVIEW_PENDING'
          : d.risk?.decision,
      });
      load();
    } catch (e) {
      setError(e.message || 'Analysis failed');
    } finally {
      setLoading(false);
    }
  }

  async function paypal() {
    if (!payment?.payment_id) return;

    setPayLoading(true);
    setError('');

    try {
      const r = await apiFetch(
        `${API}/api/payments/${payment.payment_id}/paypal/create`,
        { method: 'POST' }
      );

      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'PayPal order failed');

      setPayment((current) => ({
        ...current,
        status: d.status || 'PAYPAL_PENDING_APPROVAL',
        paypal: {
          ...(current?.paypal || {}),
          paypal_order_id: d.paypal_order_id,
          status: d.status,
          approval_url: d.approval_url,
        },
      }));

      if (d.status === 'COMPLETED') {
        localStorage.removeItem('pathguard_paypal_payment_id');
        setPayment((current) => ({
          ...current,
          status: 'COMPLETED',
          paypal: {
            ...(current?.paypal || {}),
            paypal_order_id: d.paypal_order_id,
            status: d.status,
            capture_id: d.capture_id,
          },
        }));
        setPaypalResult({
          state: 'completed',
          paymentId: d.payment_id,
          orderId: d.paypal_order_id,
          captureId: d.capture_id,
        });
        setPayLoading(false);
        await restorePayment(payment.payment_id);
        load();
        return;
      }

      if (d.approval_url) {
        localStorage.setItem('pathguard_paypal_payment_id', String(payment.payment_id));
        window.location.href = d.approval_url;
      } else {
        throw new Error('PayPal did not return an approval URL or a completed payment status');
      }
    } catch (e) {
      setError(e.message || 'PayPal order failed');
      setPayLoading(false);
    }
  }

  const risk = payment?.risk;
  const decision = risk?.decision;
  const currentStatus = payment?.status || decision;

  if (authLoading) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <div className="logo"><ShieldCheck /></div>
          <h1>PathGuard Pay</h1>
          <p>Verifying your secure session…</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="auth-shell">
        <div className="auth-layout">
          <section className="auth-story">
            <div className="brand auth-brand"><div className="logo"><ShieldCheck /></div><div><b>PathGuard Pay</b><small>Payment protection</small></div></div>
            <span className="auth-overline">A safer way to pay</span>
            <h1>Know what happens before money moves.</h1>
            <p>PathGuard checks each payment request against risk signals and your spending limits before it reaches checkout.</p>
            <div className="auth-steps">
              <Step n="01" t="Describe the payment" d="Tell the payment agent who you are paying and why." />
              <Step n="02" t="Review the decision" d="See the recipient, amount and safety checks in one place." />
              <Step n="03" t="Continue with confidence" d="Approved payments can continue to PayPal checkout." />
            </div>
            <small className="auth-sandbox"><ShieldCheck /> PayPal Sandbox · No real money is moved</small>
          </section>
          <form className="auth-card" onSubmit={submitAuth}>
          <div className="eyebrow">YOUR ACCOUNT</div>
          <h2>{authMode === 'register' ? 'Create your account' : 'Sign in'}</h2>
          <p>{authMode === 'register'
            ? 'Your payments and spending limits are private to your account.'
            : 'Enter your details to continue to PathGuard Pay.'}</p>
          {authMode === 'register' && (
            <label className="auth-field">Display name
              <input autoComplete="name" required maxLength={120} value={authName} onChange={(event) => setAuthName(event.target.value)} />
            </label>
          )}
          <label className="auth-field">Email
            <input type="email" autoComplete="email" required value={authEmail} onChange={(event) => setAuthEmail(event.target.value)} />
          </label>
          <label className="auth-field">Password
            <input type="password" autoComplete={authMode === 'register' ? 'new-password' : 'current-password'} minLength={authMode === 'register' ? 12 : 1} required value={authPassword} onChange={(event) => setAuthPassword(event.target.value)} />
          </label>
          {authMode === 'register' && <small className="auth-note">Use at least 12 characters. Staff roles are assigned separately by an administrator.</small>}
          {authError && <div className="error">{authError}</div>}
          <button className="primary auth-submit" type="submit" disabled={authBusy}>
            {authBusy ? 'Please wait…' : authMode === 'register' ? 'Create account' : 'Sign in'}
          </button>
          <button className="auth-switch" type="button" onClick={() => {
            setAuthMode((mode) => mode === 'register' ? 'login' : 'register');
            setAuthError('');
          }}>
            {authMode === 'register' ? 'Already have an account? Sign in' : 'New to PathGuard Pay? Create an account'}
          </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <>
      <header>
        <div className="brand">
          <div className="logo"><ShieldCheck /></div>
          <div>
            <b>PathGuard Pay</b>
            <small>Payment protection workspace</small>
          </div>
        </div>
        <nav className="workspace-nav" aria-label="Main navigation">
          <button className={activeTab === 'overview' ? 'nav-active' : ''} onClick={() => setActiveTab('overview')}><Activity /> Overview</button>
          <button className={activeTab === 'activity' ? 'nav-active' : ''} onClick={() => setActiveTab('activity')}><History /> Activity</button>
          <button className={activeTab === 'notifications' ? 'nav-active' : ''} onClick={() => setActiveTab('notifications')}><Bell /> Notifications{notifications.length > 0 && <span className="nav-count">{notifications.length}</span>}</button>
          {user.role === 'admin' && <button className={activeTab === 'admin' ? 'nav-active' : ''} onClick={() => setActiveTab('admin')}><Users /> Admin</button>}
        </nav>
        <div className="account-controls">
          <span className="user-avatar">{(user.display_name || 'U').slice(0, 1).toUpperCase()}</span>
          <span className="account-label"><b>{user.display_name}</b><small>{user.role}</small></span>
          <button className="signout" onClick={signOut}>Sign out</button>
        </div>
      </header>

      <main className={activeTab !== 'overview' ? 'single-view' : ''}>
        {activeTab === 'admin' && user.role === 'admin' ? <AdminDashboard /> : activeTab === 'activity' ? <section className="tab-page">
          <div className="page-heading"><div className="eyebrow">PAYMENTS</div><h1>Activity</h1><p>Review your recent payment requests and their status.</p></div>
          <div className="card info activity-page"><h3><History /> Recent activity</h3>
            {history.length ? history.map((x) => { const meta = statusMeta(x.status); return <div className="row" key={x.id}><div className={`status ${meta.tone}`}>{meta.icon}</div><div><b>{x.recipient}</b><small>{x.purpose || 'Payment'}</small><span className="activity-status">{meta.label}</span></div><strong>{x.currency} {Number(x.amount).toLocaleString()}</strong></div>; }) : <p className="muted">Your payment activity will appear here.</p>}
          </div>
        </section> : activeTab === 'notifications' ? <section className="tab-page">
          <div className="page-heading"><div className="eyebrow">ACCOUNT UPDATES</div><h1>Notifications</h1><p>Recent payment and policy events from your account.</p></div>
          <div className="card info notifications-page"><h3><Bell /> Recent notifications <span className="queue-count">{notifications.length}</span></h3>
            {notifications.length ? notifications.map((item) => <div className="notification-item" key={item.id}><span className={`notification-dot ${item.severity}`}></span><div className="notification-content"><div className="notification-title-row"><b>{item.title}</b><span className={`incident-severity ${item.severity}`}>{item.severity}</span></div><p>{item.message}</p><small>{item.recipient} · {item.currency} {Number(item.amount).toLocaleString()} · {item.created_at ? new Date(item.created_at).toLocaleString() : ''}</small></div></div>) : <p className="muted">No recent notifications.</p>}
          </div>
        </section> : <>
        <section>
          {paypalResult?.state === 'completed' && (
            <div className="result-card completed">
              <div className="result-icon"><PartyPopper /></div>
              <div className="result-copy">
                <span className="result-kicker">PAYMENT COMPLETE</span>
                <b>Payment completed successfully.</b>
                <small>PathGuard cleared the payment and PayPal Sandbox captured it.</small>
                {paypalResult.orderId && <small>Order ID: {paypalResult.orderId}</small>}
                {paypalResult.captureId && <small>Capture ID: {paypalResult.captureId}</small>}
              </div>
              <CheckCircle2 className="result-check" />
            </div>
          )}

          {paypalResult?.state === 'approved' && (
            <div className="result-card completed">
              <div className="result-icon"><CheckCircle2 /></div>
              <div className="result-copy">
                <span className="result-kicker">PAYPAL APPROVED</span>
                <b>Payment approved by PayPal.</b>
                <small>The server is finishing the capture.</small>
                {paypalResult.orderId && <small>Order ID: {paypalResult.orderId}</small>}
              </div>
            </div>
          )}

          {paypalResult?.state === 'reauth' && (
            <div className="result-card pending">
              <div className="result-icon"><ShieldAlert /></div>
              <div className="result-copy">
                <span className="result-kicker">PAYPAL CHECKOUT REFRESHED</span>
                <b>A fresh PayPal checkout is required.</b>
                <small>The previous checkout was no longer available, so PathGuard created a new one.</small>
              </div>
            </div>
          )}

          {paypalResult?.state === 'pending' && (
            <div className="result-card pending">
              <div className="result-icon"><Clock3 /></div>
              <div className="result-copy">
                <span className="result-kicker">PROCESSING</span>
                <b>Payment is still processing.</b>
                <small>PayPal approved the order, but the capture has not completed yet.</small>
              </div>
            </div>
          )}

          {paypalResult?.state === 'cancelled' && (
            <div className="result-card pending">
              <div className="result-icon"><XCircle /></div>
              <div className="result-copy">
                <span className="result-kicker">CHECKOUT CANCELLED</span>
                <b>PayPal checkout was cancelled.</b>
                <small>No payment was captured.</small>
              </div>
            </div>
          )}

          {paypalResult?.state === 'error' && (
            <div className="result-card failed">
              <div className="result-icon"><ShieldAlert /></div>
              <div className="result-copy">
                <span className="result-kicker">PAYMENT ERROR</span>
                <b>PayPal could not complete the payment.</b>
                {paypalResult.message && <small>{paypalResult.message}</small>}
              </div>
            </div>
          )}

          <div className="welcome-row"><div><div className="eyebrow">PAYMENTS OVERVIEW <span className="live-dot" /> LIVE WORKSPACE</div>
          <h1>Payment command center</h1></div><span className="sandbox"><i /> PayPal Sandbox</span></div>
          <p className="intro">
            Create a payment request and review its safety decision before checkout.
          </p>

          <div className="card composer">
            <div className="composer-heading"><div><span className="composer-icon"><ArrowRight /></span><span><label>New payment request</label><small>Describe the payment in your own words</small></span></div><span className="secure-label"><ShieldCheck /> PROTECTED</span></div>
            <textarea
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder={'For example: “Pay Jordan $240 for the brand identity project”'}
              onKeyDown={(e) => {
                if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') analyze();
              }}
            />

            <div className="bottom">
              <div className="chips">
                {[
                  'Pay John $200 for the website',
                  'Pay Sarah $150 for the logo',
                  'Pay John $10000 for the website',
                ].map((x) => (
                  <button key={x} onClick={() => setInstruction(x)}>{x}</button>
                ))}
              </div>

              <button
                className="primary"
                disabled={loading || !instruction.trim()}
                onClick={analyze}
              >
                {loading ? (
                  <><Loader2 className="spin" /> Analyzing</>
                ) : (
                  <>Analyze payment <ArrowRight /></>
                )}
              </button>
            </div>
          </div>

          {error && <div className="error"><ShieldAlert /> <span>{error}</span></div>}

          {payment && (
            <Risk
              payment={payment}
              decision={decision}
              status={currentStatus}
              loading={payLoading}
              onPay={paypal}
            />
          )}
        </section>

        <aside>
          <div className="card info limits-card paypal-connection-card">
            <h3><Link2 /> PayPal account</h3>
            {paypalConnection.connected ? (
              <>
                <div className="paypal-connection-state">
                  <CheckCircle2 />
                  <div>
                    <b>Sandbox wallet connected</b>
                    <small>{paypalConnection.email_address || 'Your PayPal wallet is linked to this PathGuard account.'}</small>
                  </div>
                </div>
                <p className="limits-intro">After PathGuard approves a payment, the saved wallet can be used to complete it. PayPal may still redirect you when additional payer action is required.</p>
              </>
            ) : (
              <p className="limits-intro">Connect your PayPal Sandbox wallet once. PayPal will ask you to sign in and authorize saving the wallet for future payments.</p>
            )}
            {paypalConnectionError && <div className="error limits-feedback">{paypalConnectionError}</div>}
            {paypalConnectionNotice && <p className="limits-saved">{paypalConnectionNotice}</p>}
            <button
              className={paypalConnection.connected ? 'signout paypal-disconnect' : 'primary limits-save'}
              disabled={paypalConnectionBusy}
              onClick={paypalConnection.connected ? disconnectPaypal : connectPaypal}
            >
              {paypalConnectionBusy
                ? <><Loader2 className="spin" /> {paypalConnection.connected ? 'Disconnecting…' : 'Connecting to PayPal…'}</>
                : paypalConnection.connected
                  ? <><Unlink /> Disconnect PayPal</>
                  : <><Link2 /> Connect PayPal</>}
            </button>
            <small className="limits-footnote">Connecting a wallet is separate from PathGuard approval. Every payment still passes risk checks, manual review when required, and your spending limits. A saved wallet may be charged without a separate PayPal checkout confirmation for every payment; use this connection only if you consent to that flow.</small>
          </div>

          <div className="card info limits-card">
            <h3><Settings2 /> Spending limits</h3>
            <p className="limits-intro">Set your budget before paying. PathGuard checks these caps before creating a PayPal order and again before capture.</p>
            <div className="limits-grid">
              <label className="limit-field">Daily limit (USD)
                <input type="number" min="0.01" step="0.01" value={limitDraft.daily_limit ?? ''} onChange={(e) => setLimitDraft((d) => ({ ...d, daily_limit: e.target.value === '' ? null : Number(e.target.value) }))} />
              </label>
              <label className="limit-field">Weekly limit (USD)
                <input type="number" min="0.01" step="0.01" value={limitDraft.weekly_limit ?? ''} onChange={(e) => setLimitDraft((d) => ({ ...d, weekly_limit: e.target.value === '' ? null : Number(e.target.value) }))} />
              </label>
              <label className="limit-field">Monthly limit (USD)
                <input type="number" min="0.01" step="0.01" value={limitDraft.monthly_limit ?? ''} onChange={(e) => setLimitDraft((d) => ({ ...d, monthly_limit: e.target.value === '' ? null : Number(e.target.value) }))} />
              </label>
              <label className="limit-field">Per-payment cap (optional)
                <input type="number" min="0.01" step="0.01" placeholder="No separate cap" value={limitDraft.per_transaction_limit ?? ''} onChange={(e) => setLimitDraft((d) => ({ ...d, per_transaction_limit: e.target.value === '' ? null : Number(e.target.value) }))} />
              </label>
              <label className="limit-field limit-timezone">Reset periods in
                <select value={limitDraft.timezone || 'Africa/Lagos'} onChange={(e) => setLimitDraft((d) => ({ ...d, timezone: e.target.value }))}>
                  <option value="Africa/Lagos">Nigeria (Africa/Lagos)</option>
                  <option value="UTC">UTC</option>
                  <option value="Europe/London">United Kingdom (Europe/London)</option>
                  <option value="America/New_York">US Eastern (America/New_York)</option>
                </select>
              </label>
            </div>
            {limitSummary && (
              <div className="limits-usage">
                <b>Current usage · includes active reservations</b>
                <div><span>Today</span><strong>USD {Number(limitSummary.daily_used || 0).toLocaleString()} / {limitSummary.daily_limit == null ? 'No cap' : Number(limitSummary.daily_limit).toLocaleString()}</strong></div>
                <div><span>This week</span><strong>USD {Number(limitSummary.weekly_used || 0).toLocaleString()} / {limitSummary.weekly_limit == null ? 'No cap' : Number(limitSummary.weekly_limit).toLocaleString()}</strong></div>
                <div><span>This month</span><strong>USD {Number(limitSummary.monthly_used || 0).toLocaleString()} / {limitSummary.monthly_limit == null ? 'No cap' : Number(limitSummary.monthly_limit).toLocaleString()}</strong></div>
                <small>Active reservations release when checkout is cancelled or the reservation expires. Only completed payments count as actual spend.</small>
              </div>
            )}
            {limitsError && <div className="error limits-feedback">{limitsError}</div>}
            {limitsSaved && <p className="limits-saved">{limitsSaved}</p>}
            <button className="primary limits-save" disabled={limitsSaving} onClick={saveLimits}>
              {limitsSaving ? <><Loader2 className="spin" /> Saving limits…</> : <><Save /> Save spending limits</>}
            </button>
            <small className="limits-footnote">These limits and payment history apply only to your account. Limits are denominated in USD; non-USD payments are blocked until currency conversion is supported.</small>
          </div>

          <div className="card info">
            <h3><Activity /> Payment intelligence</h3>
            <p className="limits-intro">
              {intelligenceOverview?.scope === 'organization'
                ? 'Operational signals across the organization.'
                : 'Your account-level payment outcomes and recurring signals.'}
            </p>
            {intelligenceOverview ? (
              <>
                <div className="intelligence-metrics">
                  <div><span>Total attempts</span><b>{Number(intelligenceOverview.total_payments || 0).toLocaleString()}</b></div>
                  <div><span>Completed spend</span><b>${Number(intelligenceOverview.completed_spend_usd || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}</b></div>
                  <div><span>Completed</span><b>{Number(intelligenceOverview.completed_payments || 0).toLocaleString()}</b></div>
                  <div><span>Blocked</span><b>{Number(intelligenceOverview.blocked_payments || 0).toLocaleString()}</b></div>
                  <div><span>Awaiting review</span><b>{Number(intelligenceOverview.awaiting_review || 0).toLocaleString()}</b></div>
                  <div><span>Success rate</span><b>{Number(intelligenceOverview.success_rate_percent || 0).toLocaleString()}%</b></div>
                </div>
                <div className="intelligence-submetrics">
                  <span><CircleDollarSign /> Limit blocks: {Number(intelligenceOverview.spending_limit_blocks || 0).toLocaleString()}</span>
                  <span><TrendingUp /> PayPal errors: {Number(intelligenceOverview.paypal_errors || 0).toLocaleString()}</span>
                </div>
              </>
            ) : <p className="muted">Intelligence metrics are loading.</p>}
            <div className="ai-summary-controls">
              <button className="ai-summary-button" onClick={generateSummary} disabled={summaryLoading}>
                {summaryLoading ? <><Loader2 className="spin" /> Generating summary…</> : <><Activity /> Generate AI investigation summary</>}
              </button>
              {summaryError && <div className="error limits-feedback">{summaryError}</div>}
            </div>
            {intelligenceSummary && (
              <div className="ai-summary-block">
                <div className="ai-summary-heading">
                  <b>Investigation summary</b>
                  <span>{intelligenceSummary.source === 'openrouter' ? 'OpenRouter AI' : 'Rule-based fallback'}</span>
                </div>
                <p>{intelligenceSummary.summary}</p>
                {intelligenceSummary.priority_actions?.length > 0 && (
                  <div className="ai-priority-actions">
                    <strong>Priority actions</strong>
                    {intelligenceSummary.priority_actions.map((action) => (
                      <div key={action.title}>
                        <span className={`incident-severity ${action.severity}`}>{action.severity}</span>
                        <span><b>{action.title}</b><small>{action.action}</small></span>
                      </div>
                    ))}
                  </div>
                )}
                <small className="limits-footnote">{intelligenceSummary.disclaimer}</small>
              </div>
            )}
            <div className="incident-heading">
              <b><AlertTriangle /> Recent incident signals</b>
              <span>{incidents.length}</span>
            </div>
            {incidents.length ? incidents.map((incident) => (
              <div className="incident-item" key={incident.id}>
                <div className="incident-title-row">
                  <b>{incident.title}</b>
                  <span className={`incident-severity ${incident.severity}`}>{incident.severity}</span>
                </div>
                <small>{incident.event_count_24h} events in 24h · {incident.affected_payments} affected payment(s)</small>
                <p>{incident.summary}</p>
                <div className="incident-action"><strong>Next step:</strong> {incident.recommended_action}</div>
              </div>
            )) : (
              <p className="muted">No recurring incident patterns met the detection threshold in the last 24 hours.</p>
            )}
            <small className="limits-footnote">Signals are based on recorded audit events, not predictions. Suggested actions are guidance only; they never bypass risk decisions or spending limits.</small>
          </div>

          {['reviewer', 'admin'].includes(user.role) && <div className="card info">
            <h3><Clock3 /> Human review queue <span className="queue-count">{reviewQueue.length}</span></h3>
            {reviewQueue.length ? reviewQueue.map((item) => (
              <div className="review-item" key={item.id}>
                <div className="review-meta">
                  <b>{item.recipient}</b>
                  <strong>{item.currency} {Number(item.amount).toLocaleString()}</strong>
                </div>
                <small>{item.purpose || 'Payment'} · Risk {item.risk?.score ?? '—'}/100</small>
                {item.risk?.reasons?.slice(0, 2).map((reason, i) => (
                  <small className="review-reason" key={i}>• {reason}</small>
                ))}
                <div className="review-actions">
                  <button disabled={reviewLoading} onClick={() => decideReview(item, 'approve')}>Approve</button>
                  <button disabled={reviewLoading} onClick={() => decideReview(item, 'reject')}>Reject</button>
                </div>
              </div>
            )) : <p className="muted">No payments are waiting for review.</p>}
          </div>}

        </aside>
        </>}
      </main>

      <footer>PathGuard Pay · AI → PathGuard → PayPal</footer>
    </>
  );
}

function Step({ n, t, d }) {
  return (
    <div className="step">
      <em>{n}</em>
      <div><b>{t}</b><small>{d}</small></div>
    </div>
  );
}


function AdminDashboard() {
  const [overview, setOverview] = useState(null);
  const [users, setUsers] = useState([]);
  const [payments, setPayments] = useState([]);
  const [query, setQuery] = useState('');
  const [paymentQuery, setPaymentQuery] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [view, setView] = useState('users');

  async function refresh() {
    setError('');
    try {
      const responses = await Promise.all([
        apiFetch(API + '/api/admin/overview'),
        apiFetch(API + '/api/admin/users?limit=100'),
        apiFetch(API + '/api/admin/payments?limit=100'),
      ]);
      for (const response of responses) {
        if (response.status === 403 || response.status === 401) throw new Error('Administrator permission is required to access this section.');
        if (!response.ok) throw new Error('Could not load administrator data.');
      }
      const data = await Promise.all(responses.map((response) => response.json()));
      setOverview(data[0]);
      setUsers(data[1].items || []);
      setPayments(data[2].items || []);
    } catch (e) {
      setError(e.message || 'Could not load administrator data.');
    }
  }

  useEffect(() => { refresh(); }, []);

  async function searchUsers(event) {
    event.preventDefault();
    try {
      const response = await apiFetch(API + '/api/admin/users?limit=100&q=' + encodeURIComponent(query));
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not search users.');
      setUsers(data.items || []);
    } catch (e) { setError(e.message); }
  }

  async function updateUser(account, patch) {
    setBusyId(account.id);
    setError('');
    setNotice('');
    try {
      const response = await apiFetch(API + '/api/admin/users/' + account.id, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not update user.');
      setNotice('Updated ' + data.email + ' successfully.');
      await refresh();
    } catch (e) { setError(e.message || 'Could not update user.'); }
    finally { setBusyId(null); }
  }

  const visiblePayments = payments.filter((item) => [item.user_email, item.recipient, item.status, item.purpose].filter(Boolean).join(' ').toLowerCase().includes(paymentQuery.toLowerCase()));
  const money = (value) => Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
  const date = (value) => value ? new Date(value).toLocaleDateString() : '—';

  return <section className="tab-page admin-page">
    <div className="page-heading admin-heading"><div><div className="eyebrow">PLATFORM CONTROL</div><h1>Admin dashboard</h1><p>Manage accounts and monitor every PathGuard Pay payment.</p></div><button className="admin-refresh" onClick={refresh}><RefreshCw /> Refresh data</button></div>
    {error && <div className="error"><ShieldAlert /><span>{error}</span></div>}
    {notice && <div className="admin-notice"><CheckCircle2 />{notice}</div>}
    <div className="admin-metrics">
      {[['Registered users', overview?.users_total, Users], ['Active users', overview?.active_users, CheckCircle2], ['All payments', overview?.payments_total, History], ['Completed volume', '
  const decisionConfig = {
    ALLOW: ['allow', <CheckCircle2 />, 'Payment approved'],
    REVIEW: ['review', <Clock3 />, 'Payment needs review'],
    BLOCK: ['block', <ShieldX />, 'Payment blocked'],
  };

  const cfg = decisionConfig[decision] || ['review', <ShieldAlert />, 'Payment result'];
  const reasons = Array.isArray(payment?.risk?.reasons) ? payment.risk.reasons : [];
  const amount = Number(payment?.intent?.amount || 0);
  const meta = statusMeta(status);

  const canPay =
    decision === 'ALLOW' ||
    (decision === 'REVIEW' && status === 'REVIEW_APPROVED');

  let message = 'Review the payment details before continuing.';
  if (status === 'REVIEW_PENDING') message = 'A human reviewer must approve this payment before PayPal can be used.';
  if (status === 'REVIEW_APPROVED') message = 'Human review passed. This payment can now continue to PayPal.';
  if (status === 'REVIEW_REJECTED') message = 'A human reviewer rejected this payment. No PayPal order can be created.';
  if (status === 'PAYPAL_PENDING_APPROVAL') message = 'A PayPal order exists. Complete the Sandbox checkout to continue.';
  if (status === 'PAYPAL_PENDING_CAPTURE') message = 'PayPal approved the order. PathGuard is completing the capture.';
  if (status === 'COMPLETED') message = 'Payment completed successfully. No further action is required.';

  return (
    <div className={`card risk ${cfg[0]}`}>
      <div className="riskhead">
        <div className="riskicon">{cfg[1]}</div>
        <div className="risk-title">
          <small>PATHGUARD DECISION</small>
          <h2>{cfg[2]}</h2>
          <p>{message}</p>
        </div>
        <div className="score">
          <b>{payment?.risk?.risk_score ?? 0}</b><small>/100</small>
        </div>
      </div>

      <div className="lifecycle">
        <span className="lifecycle-label">PAYMENT STATUS</span>
        <div className={`lifecycle-status ${meta.tone}`}>
          {meta.icon}<b>{meta.label}</b>
        </div>
      </div>

      <div className="summary">
        <div><small>RECIPIENT</small><b>{payment?.intent?.recipient_name || 'Unknown'}</b></div>
        <div><small>AMOUNT</small><b>{payment?.intent?.currency || 'USD'} {amount.toLocaleString()}</b></div>
        <div><small>PURPOSE</small><b>{payment?.intent?.purpose || 'Payment'}</b></div>
      </div>

      <div className="reasons">
        <b><ShieldAlert /> Why PathGuard decided this</b>
        {reasons.length
          ? reasons.map((r, i) => <p key={`${r}-${i}`}>✓ {r}</p>)
          : <p>✓ No additional risk reasons were reported.</p>}
      </div>

      {decision === 'BLOCK' ? (
        <div className="blocked"><ShieldX /> {payment?.paypal ? 'Payment blocked before capture. PathGuard did not capture the existing PayPal order.' : 'No PayPal order was created.'}</div>
      ) : status === 'REVIEW_REJECTED' ? (
        <div className="blocked review-rejected"><ShieldX /> This payment was rejected during human review.</div>
      ) : status === 'REVIEW_PENDING' ? (
        <div className="blocked review-held"><Clock3 /> Waiting for human approval before PayPal.</div>
      ) : status === 'COMPLETED' ? (
        <div className="completed-inline"><CheckCircle2 /> Payment captured successfully.</div>
      ) : status === 'PAYPAL_PENDING_APPROVAL' ? (
        <div className="blocked paypal-held"><Clock3 /> PayPal checkout is awaiting approval.</div>
      ) : status === 'PAYPAL_PENDING_CAPTURE' ? (
        <div className="blocked paypal-held"><Loader2 className="spin" /> PayPal approved. Capture is in progress.</div>
      ) : canPay ? (
        <button className="paypal" disabled={loading} onClick={onPay}>
          {loading
            ? <><Loader2 className="spin" /> Creating PayPal order…</>
            : <>Continue with PayPal <ArrowRight /></>}
        </button>
      ) : null}
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
 + money(overview?.completed_payment_volume), CircleDollarSign], ['Blocked', overview?.blocked_payments, ShieldX], ['Pending', overview?.pending_payments, Clock3]].map(([label, value, Icon]) => <div className="card admin-metric" key={label}><span><Icon /></span><small>{label}</small><b>{value ?? '—'}</b></div>)}
    </div>
    <div className="admin-switch"><button className={view === 'users' ? 'selected' : ''} onClick={() => setView('users')}><Users /> User management</button><button className={view === 'payments' ? 'selected' : ''} onClick={() => setView('payments')}><History /> All payments</button></div>
    {view === 'users' ? <div className="card admin-table-card">
      <div className="admin-table-heading"><div><h2>Users</h2><p>Search accounts, review roles, and manage access.</p></div><form className="admin-search" onSubmit={searchUsers}><Search /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search name or email" /><button type="submit">Search</button></form></div>
      <div className="admin-table-scroll"><table className="admin-table"><thead><tr><th>User</th><th>Role</th><th>Payments</th><th>Joined</th><th>Status</th><th>Actions</th></tr></thead><tbody>{users.map((account) => <tr key={account.id}><td><b>{account.display_name}</b><small>{account.email}</small><small>Account #{account.id}</small></td><td><select aria-label={'Role for ' + account.email} value={account.role} disabled={busyId === account.id} onChange={(e) => updateUser(account, { role: e.target.value })}><option value="customer">Customer</option><option value="reviewer">Reviewer</option><option value="admin">Admin</option></select></td><td>{account.payment_count}</td><td>{date(account.created_at)}</td><td><span className={'admin-state ' + (account.is_active ? 'active' : 'inactive')}>{account.is_active ? 'Active' : 'Inactive'}</span></td><td><button className={'admin-action ' + (account.is_active ? 'deactivate' : 'activate')} disabled={busyId === account.id} onClick={() => updateUser(account, { is_active: !account.is_active })}>{busyId === account.id ? 'Saving…' : account.is_active ? 'Deactivate' : 'Reactivate'}</button></td></tr>)}</tbody></table>{!users.length && <p className="muted admin-empty">No users match this search.</p>}</div>
    </div> : <div className="card admin-table-card"><div className="admin-table-heading"><div><h2>All payments</h2><p>Platform-wide payment activity and risk decisions.</p></div><div className="admin-search"><Search /><input value={paymentQuery} onChange={(e) => setPaymentQuery(e.target.value)} placeholder="Search payment, user, status" /></div></div><div className="admin-table-scroll"><table className="admin-table"><thead><tr><th>Payment</th><th>Account</th><th>Amount</th><th>Risk</th><th>Status</th><th>Created</th></tr></thead><tbody>{visiblePayments.map((item) => <tr key={item.id}><td><b>#{item.id} · {item.recipient}</b><small>{item.purpose || 'Payment'}</small></td><td>{item.user_email}</td><td>{item.currency} {money(item.amount)}</td><td>{item.risk_score ?? '—'}{item.risk_decision ? <small>{item.risk_decision}</small> : null}</td><td><span className={'admin-state ' + (item.status === 'COMPLETED' ? 'active' : item.status === 'BLOCK' ? 'inactive' : 'pending')}>{item.status}</span></td><td>{date(item.created_at)}</td></tr>)}</tbody></table>{!visiblePayments.length && <p className="muted admin-empty">No payments match this search.</p>}</div></div>}
    <p className="admin-footnote">Sensitive account controls are available only to administrators. Changes are enforced by the backend.</p>
  </section>;
}

function Risk({ payment, decision, status, loading, onPay }) {
  const decisionConfig = {
    ALLOW: ['allow', <CheckCircle2 />, 'Payment approved'],
    REVIEW: ['review', <Clock3 />, 'Payment needs review'],
    BLOCK: ['block', <ShieldX />, 'Payment blocked'],
  };

  const cfg = decisionConfig[decision] || ['review', <ShieldAlert />, 'Payment result'];
  const reasons = Array.isArray(payment?.risk?.reasons) ? payment.risk.reasons : [];
  const amount = Number(payment?.intent?.amount || 0);
  const meta = statusMeta(status);

  const canPay =
    decision === 'ALLOW' ||
    (decision === 'REVIEW' && status === 'REVIEW_APPROVED');

  let message = 'Review the payment details before continuing.';
  if (status === 'REVIEW_PENDING') message = 'A human reviewer must approve this payment before PayPal can be used.';
  if (status === 'REVIEW_APPROVED') message = 'Human review passed. This payment can now continue to PayPal.';
  if (status === 'REVIEW_REJECTED') message = 'A human reviewer rejected this payment. No PayPal order can be created.';
  if (status === 'PAYPAL_PENDING_APPROVAL') message = 'A PayPal order exists. Complete the Sandbox checkout to continue.';
  if (status === 'PAYPAL_PENDING_CAPTURE') message = 'PayPal approved the order. PathGuard is completing the capture.';
  if (status === 'COMPLETED') message = 'Payment completed successfully. No further action is required.';

  return (
    <div className={`card risk ${cfg[0]}`}>
      <div className="riskhead">
        <div className="riskicon">{cfg[1]}</div>
        <div className="risk-title">
          <small>PATHGUARD DECISION</small>
          <h2>{cfg[2]}</h2>
          <p>{message}</p>
        </div>
        <div className="score">
          <b>{payment?.risk?.risk_score ?? 0}</b><small>/100</small>
        </div>
      </div>

      <div className="lifecycle">
        <span className="lifecycle-label">PAYMENT STATUS</span>
        <div className={`lifecycle-status ${meta.tone}`}>
          {meta.icon}<b>{meta.label}</b>
        </div>
      </div>

      <div className="summary">
        <div><small>RECIPIENT</small><b>{payment?.intent?.recipient_name || 'Unknown'}</b></div>
        <div><small>AMOUNT</small><b>{payment?.intent?.currency || 'USD'} {amount.toLocaleString()}</b></div>
        <div><small>PURPOSE</small><b>{payment?.intent?.purpose || 'Payment'}</b></div>
      </div>

      <div className="reasons">
        <b><ShieldAlert /> Why PathGuard decided this</b>
        {reasons.length
          ? reasons.map((r, i) => <p key={`${r}-${i}`}>✓ {r}</p>)
          : <p>✓ No additional risk reasons were reported.</p>}
      </div>

      {decision === 'BLOCK' ? (
        <div className="blocked"><ShieldX /> {payment?.paypal ? 'Payment blocked before capture. PathGuard did not capture the existing PayPal order.' : 'No PayPal order was created.'}</div>
      ) : status === 'REVIEW_REJECTED' ? (
        <div className="blocked review-rejected"><ShieldX /> This payment was rejected during human review.</div>
      ) : status === 'REVIEW_PENDING' ? (
        <div className="blocked review-held"><Clock3 /> Waiting for human approval before PayPal.</div>
      ) : status === 'COMPLETED' ? (
        <div className="completed-inline"><CheckCircle2 /> Payment captured successfully.</div>
      ) : status === 'PAYPAL_PENDING_APPROVAL' ? (
        <div className="blocked paypal-held"><Clock3 /> PayPal checkout is awaiting approval.</div>
      ) : status === 'PAYPAL_PENDING_CAPTURE' ? (
        <div className="blocked paypal-held"><Loader2 className="spin" /> PayPal approved. Capture is in progress.</div>
      ) : canPay ? (
        <button className="paypal" disabled={loading} onClick={onPay}>
          {loading
            ? <><Loader2 className="spin" /> Creating PayPal order…</>
            : <>Continue with PayPal <ArrowRight /></>}
        </button>
      ) : null}
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
