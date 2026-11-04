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
  ClipboardCheck,
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
  CreditCard,
  Wallet,
  Shield,
  LayoutDashboard,
  Users,
  Search,
  RefreshCw,
  Plus,
  ArrowUpRight,
  ArrowDownLeft,
  ChevronRight,
  Menu,
  X,
  LogOut,
  Sparkles,
  Eye,
  EyeOff,
  LockKeyhole,
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
  ALLOW: 'Checks passed',
  BLOCK: 'Blocked',
  REVIEW_PENDING: 'Awaiting review',
  REVIEW_APPROVED: 'Review approved',
  REVIEW_REJECTED: 'Review rejected',
  PAYPAL_PENDING_APPROVAL: 'Awaiting PayPal approval',
  PAYPAL_PENDING_CAPTURE: 'Capturing payment',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
  PAYPAL_CAPTURE_ERROR: 'Checkout issue',
  ANALYZED: 'Checked',
  REVIEW: 'Needs review',
};

function statusMeta(status) {
  if (['BLOCK', 'REVIEW_REJECTED', 'PAYPAL_CAPTURE_ERROR'].includes(status)) {
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
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  function navigate(tab) { setActiveTab(tab); setMobileNavOpen(false); }
  useEffect(() => {
    if (!mobileNavOpen) return;
    const close = (event) => { if (event.key === 'Escape') setMobileNavOpen(false); };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [mobileNavOpen]);
  const [instruction, setInstruction] = useState('');
  const [payment, setPayment] = useState(null);
  const [history, setHistory] = useState([]);
  const [ownReviews, setOwnReviews] = useState([]);
  const [reviewPasswords, setReviewPasswords] = useState({});
  const [ownReviewBusyId, setOwnReviewBusyId] = useState(null);
  const [ownReviewError, setOwnReviewError] = useState('');
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

      const ownReviewsResponse = await apiFetch(`${API}/api/reviews/mine`);
      if (ownReviewsResponse.ok) setOwnReviews(await ownReviewsResponse.json());

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
        let recipientProfile = null;
        try {
          const profileResponse = await apiFetch(
            `${API}/api/payments/recipients/${encodeURIComponent(d.recipient)}/history?currency=${encodeURIComponent(d.currency || 'USD')}`
          );
          if (profileResponse.ok) recipientProfile = await profileResponse.json();
        } catch {
          // Payment restoration should still work when recipient history is unavailable.
        }
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
          recipient_profile: recipientProfile,
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
    const paypalConnectReason = q.get('reason');
    const paypalStatus = q.get('paypal_status');
    const paypalCode = q.get('paypal_code');
    const paypalIssue = q.get('paypal_issue');
    const paypalDebugId = q.get('paypal_debug_id');
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
      let diagnostic = 'PayPal wallet connection failed.';
      if (paypalConnectReason === 'paypal_token_exchange_failed') {
        const errorParts = [paypalStatus && `HTTP ${paypalStatus}`, paypalCode, paypalIssue].filter(Boolean);
        diagnostic = `PayPal approved the connection, but could not save the wallet${errorParts.length ? ` (${errorParts.join(' / ')})` : ''}.`;
        if (paypalDebugId) diagnostic += ` PayPal Debug ID: ${paypalDebugId}.`;
        diagnostic += ' Check that the Sandbox app has Vault access and that its API permissions allow payment-token creation.';
      } else if (paypalConnectReason === 'missing_return_token') {
        diagnostic = 'PayPal returned to PathGuard without a setup-token identifier. Retry the wallet connection; if it repeats, share the backend callback logs.';
      } else if (paypalConnectReason === 'pending_connection_not_found') {
        diagnostic = 'PayPal returned to PathGuard, but the callback did not match the pending wallet connection. Check the callback URL and keep the backend database unchanged while retrying.';
      } else if (paypalConnectReason === 'encryption_key_invalid') {
        diagnostic = 'The PayPal token could not be encrypted. Verify PAYPAL_VAULT_ENCRYPTION_KEY is a valid Fernet key and has not changed since setup.';
      } else if (paypalConnectReason === 'invalid_token_response') {
        diagnostic = 'PayPal did not return a valid reusable wallet token. Check the backend logs for the callback error.';
      } else if (paypalConnectReason) {
        diagnostic = `PayPal wallet connection failed (${paypalConnectReason}). Check the backend logs for details.`;
      } else {
        diagnostic = 'PayPal wallet connection failed without a diagnostic code. Update the backend and frontend, then retry.';
      }
      setPaypalConnectionError(diagnostic);
      setPaypalConnectionNotice('');
    }

    if (paypalState || paymentId) setActiveTab('payments');
    else if (paypalConnectState) setActiveTab('wallet');
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
    setOwnReviews([]);
    setReviewPasswords({});
    setOwnReviewError('');
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

  async function continueApprovedReview(item) {
    setError('');
    setPayment({
      payment_id: item.id,
      intent: {
        recipient_name: item.recipient,
        amount: Number(item.amount),
        currency: item.currency || 'USD',
        purpose: item.purpose,
      },
      risk: item.risk ? {
        risk_score: item.risk.score,
        decision: item.risk.decision,
        reasons: item.risk.reasons || [],
      } : null,
      status: item.status,
      paypal: null,
      recipient_profile: null,
    });
    setActiveTab('payments');
    await paypal(false, item.id);
  }

  async function decideOwnReview(item, action) {
    setOwnReviewBusyId(item.id);
    setOwnReviewError('');
    try {
      const isConfirm = action === 'confirm';
      const password = reviewPasswords[item.id] || '';
      if (isConfirm && !password) throw new Error('Re-enter your account password to confirm this payment.');
      const response = await apiFetch(`${API}/api/reviews/${item.id}/${isConfirm ? 'confirm' : 'reject-own'}`, {
        method: 'POST',
        headers: isConfirm ? { 'Content-Type': 'application/json' } : {},
        ...(isConfirm ? { body: JSON.stringify({ password }) } : {}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not update this payment review.');
      setOwnReviews((items) => items.map((entry) => entry.id === item.id ? data : entry));
      setReviewPasswords((values) => ({ ...values, [item.id]: '' }));
      setHistory((items) => items.map((entry) => entry.id === item.id ? { ...entry, status: data.status } : entry));
      setPayment((current) => current?.payment_id === item.id ? { ...current, status: data.status } : current);
      if (payment?.payment_id === item.id) setActiveTab('payments');
      await load();
    } catch (error) {
      setOwnReviewError(error.message || 'Could not update this payment review.');
    } finally {
      setOwnReviewBusyId(null);
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
      void (async () => {
        try {
          const profileResponse = await apiFetch(
            `${API}/api/payments/recipients/${encodeURIComponent(d.intent.recipient_name)}/history?currency=${encodeURIComponent(d.intent.currency || 'USD')}`
          );
          if (profileResponse.ok) {
            const recipientProfile = await profileResponse.json();
            setPayment((current) => current?.payment_id === d.payment_id
              ? { ...current, recipient_profile: recipientProfile }
              : current);
          }
        } catch {
          // Recipient history is supplementary; the risk decision remains available.
        }
      })();
      load();
    } catch (e) {
      setError(e.message || 'Analysis failed');
    } finally {
      setLoading(false);
    }
  }

  async function paypal(useSavedWallet = false, paymentIdOverride = null) {
    const targetPaymentId = paymentIdOverride || payment?.payment_id;
    if (!targetPaymentId) return;

    setPayLoading(true);
    setError('');

    try {
      const endpoint = `${API}/api/payments/${targetPaymentId}/paypal/create${useSavedWallet ? '?use_saved_wallet=true' : ''}`;
      const r = await apiFetch(endpoint, { method: 'POST' });

      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'PayPal order failed');

      setPayment((current) => current?.payment_id === targetPaymentId ? ({
        ...current,
        status: d.status || 'PAYPAL_PENDING_APPROVAL',
        paypal: {
          ...(current?.paypal || {}),
          paypal_order_id: d.paypal_order_id,
          status: d.status,
          approval_url: d.approval_url,
        },
      }) : current);

      if (d.status === 'COMPLETED') {
        localStorage.removeItem('pathguard_paypal_payment_id');
        setPayment((current) => current?.payment_id === targetPaymentId ? ({
          ...current,
          status: 'COMPLETED',
          paypal: {
            ...(current?.paypal || {}),
            paypal_order_id: d.paypal_order_id,
            status: d.status,
            capture_id: d.capture_id,
          },
        }) : current);
        setPaypalResult({
          state: 'completed',
          paymentId: d.payment_id,
          orderId: d.paypal_order_id,
          captureId: d.capture_id,
        });
        setPayLoading(false);
        await restorePayment(targetPaymentId);
        load();
        return;
      }

      if (d.approval_url) {
        localStorage.setItem('pathguard_paypal_payment_id', String(targetPaymentId));
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
            <Brand />
            <div className="auth-story-copy"><span className="auth-overline"><span /> Thoughtful payments. By design.</span>
            <h1>A little pause.<br /><span>A safer payment.</span></h1>
            <p>Put a clear safety check between your intent and your next payment.</p></div>
            <div className="auth-visual" aria-label="Payment safety workflow">
              <div className="visual-instruction"><span><Sparkles /> YOUR INSTRUCTION</span><p>“Pay Jordan $240 for the brand identity.”</p></div>
              <div className="visual-connector" /><div className="visual-check"><span className="visual-shield"><ShieldCheck /></span><div><b>Clarity before checkout</b><small>Details · Risk signals · Spending limits</small></div><CheckCircle2 /></div>
              <div className="visual-connector" /><div className="visual-destination"><LockKeyhole /> Your decision comes first <ArrowRight /></div>
            </div>
            <small className="auth-sandbox"><ShieldCheck /> Built with PayPal Sandbox <span>No real money moves.</span></small>
          </section>
          <form className="auth-card" onSubmit={submitAuth}>
          <span className="auth-form-icon"><LockKeyhole /></span><div className="eyebrow">YOUR PAYMENT WORKSPACE</div>
          <h2>{authMode === 'register' ? 'Start with peace of mind.' : 'Welcome back.'}</h2>
          <p>{authMode === 'register'
            ? 'Your payments and spending limits are private to your account.'
            : 'Sign in to keep your next payment in check.'}</p>
          {authMode === 'register' && (
            <label className="auth-field">Display name
              <input autoComplete="name" required maxLength={120} value={authName} onChange={(event) => setAuthName(event.target.value)} />
            </label>
          )}
          <label className="auth-field">Email
            <input type="email" placeholder="you@example.com" autoComplete="email" required value={authEmail} onChange={(event) => setAuthEmail(event.target.value)} />
          </label>
          <label className="auth-field">Password
            <span className="password-input"><input type={showPassword ? 'text' : 'password'} placeholder={authMode === 'register' ? 'At least 12 characters' : 'Enter your password'} autoComplete={authMode === 'register' ? 'new-password' : 'current-password'} minLength={authMode === 'register' ? 12 : 1} required value={authPassword} onChange={(event) => setAuthPassword(event.target.value)} /><button type="button" aria-label={showPassword ? 'Hide password' : 'Show password'} onClick={() => setShowPassword(!showPassword)}>{showPassword ? <EyeOff /> : <Eye />}</button></span>
          </label>
          {authMode === 'register' && <small className="auth-note">Use at least 12 characters to protect your account.</small>}
          {authError && <div className="error">{authError}</div>}
          <button className="primary auth-submit" type="submit" disabled={authBusy}>
            {authBusy ? <><Loader2 className="spin" /> Please wait…</> : <>{authMode === 'register' ? 'Create account' : 'Sign in'} <ArrowRight /></>}
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
      <a className="skip-link" href="#workspace-main">Skip to content</a>
      {mobileNavOpen && <button className="nav-backdrop" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)} />}
      <header className={`app-sidebar ${mobileNavOpen ? 'is-open' : ''}`}>
        <Brand compact />
        <button className="sidebar-create" onClick={() => navigate('payments')}><Plus /> New payment <span>↗</span></button>
        <nav className="workspace-nav" aria-label="Main navigation">
          <span className="nav-section-label">WORKSPACE</span>
          {[
            ['overview', LayoutDashboard, 'Overview'],
            ['activity', History, 'Transactions'],
            ['reviews', ClipboardCheck, 'Payment reviews'],
            ['intelligence', Activity, 'Insights'],
          ].map(([tab, Icon, label]) => <button key={tab} aria-current={activeTab === tab ? 'page' : undefined} className={activeTab === tab ? 'nav-active' : ''} onClick={() => navigate(tab)}><Icon /> {label}{tab === 'reviews' && ownReviews.filter(x => x.status === 'REVIEW_PENDING').length > 0 && <span className="nav-count">{ownReviews.filter(x => x.status === 'REVIEW_PENDING').length}</span>}</button>)}
          <span className="nav-section-label nav-section-spaced">YOUR ACCOUNT</span>
          {[
            ['security', ShieldCheck, 'Spending & limits'],
            ['wallet', Wallet, 'Payment methods'],
            ['notifications', Bell, 'Notifications'],
            ...(user.role === 'admin' ? [['admin', Users, 'Administration']] : []),
          ].map(([tab, Icon, label]) => <button key={tab} aria-current={activeTab === tab ? 'page' : undefined} className={activeTab === tab ? 'nav-active' : ''} onClick={() => navigate(tab)}><Icon /> {label}</button>)}
        </nav>
        <div className="sidebar-note"><ShieldCheck /><b>A moment of clarity.</b><p>Every payment starts with a check. You stay in control.</p><span><i /> PayPal Sandbox</span></div>
        <div className="account-controls"><span className="user-avatar">{(user.display_name || 'U').slice(0, 1).toUpperCase()}</span><span className="account-label"><b>{user.display_name}</b><small>{user.role === 'customer' ? 'Personal workspace' : user.role}</small></span><button className="signout" title="Sign out" aria-label="Sign out" onClick={signOut}><LogOut /></button></div>
      </header>
      <div className="workspace-topbar">
        <div className="topbar-breadcrumb"><button className="mobile-menu icon-button" aria-label={mobileNavOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={mobileNavOpen} onClick={() => setMobileNavOpen(!mobileNavOpen)}>{mobileNavOpen ? <X /> : <Menu />}</button><span>Workspace</span><ChevronRight /><b>{({overview:'Overview',payments:'New payment',activity:'Transactions',reviews:'Payment reviews',intelligence:'Insights',security:'Spending & limits',wallet:'Payment methods',notifications:'Notifications',admin:'Administration'})[activeTab]}</b></div>
        <div className="topbar-actions"><span className="environment-tag"><i /> Sandbox</span><button className="icon-button" aria-label="View notifications" onClick={() => navigate('notifications')}><Bell />{notifications.length > 0 && <i />}</button><span className="topbar-avatar">{(user.display_name || 'U').slice(0,1).toUpperCase()}</span></div>
      </div>
      <main id="workspace-main" className="workspace-main" data-view={activeTab}>
        {activeTab === 'overview' && <Overview user={user} history={history} overview={intelligenceOverview} limits={limitSummary} reviews={ownReviews} navigate={navigate} openPayment={(id) => { restorePayment(id); navigate('payments'); }} />}
        {activeTab === 'admin' && user.role === 'admin' ? <AdminDashboard /> : activeTab === 'reviews' ? <section className="tab-page">
          <div className="page-heading"><div className="eyebrow">PAYMENT SAFETY</div><h1>Payment Reviews</h1><p>Review payments flagged by PathGuard before starting PayPal checkout. Your password is required to confirm a payment.</p></div>
          {ownReviewError && <div className="error"><ShieldAlert /><span>{ownReviewError}</span></div>}
          <div className="card info self-reviews-page"><h3><ClipboardCheck /> Your flagged payments <span className="queue-count">{ownReviews.filter((item) => item.status === 'REVIEW_PENDING').length}</span></h3>
            {ownReviews.length ? ownReviews.map((item) => {
              const pending = item.status === 'REVIEW_PENDING';
              const meta = statusMeta(item.status);
              return <div className="review-item self-review-item" key={item.id}>
                <div className="review-meta"><b>{item.recipient}</b><strong>{item.currency} {Number(item.amount).toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong></div>
                <small>{item.purpose || 'Payment'} · Risk {item.risk?.score ?? '—'}/100 · {item.created_at ? new Date(item.created_at).toLocaleString() : ''}</small>
                <div className={`lifecycle-status ${meta.tone}`}>{meta.icon}<b>{meta.label}</b></div>
                {item.risk?.reasons?.map((reason, index) => <small className="review-reason" key={`${item.id}-${index}`}>• {reason}</small>)}
                {item.status === 'REVIEW_APPROVED' && <div className="review-actions"><button disabled={payLoading} onClick={() => continueApprovedReview(item)}>{payLoading ? 'Preparing checkout…' : 'Continue to PayPal'} <ArrowRight /></button></div>}
                {pending ? <>
                  <label className="self-review-password">Confirm with your account password
                    <input type="password" autoComplete="current-password" value={reviewPasswords[item.id] || ''} onChange={(event) => setReviewPasswords((values) => ({ ...values, [item.id]: event.target.value }))} placeholder="Re-enter password" disabled={ownReviewBusyId === item.id} />
                  </label>
                  <p className="limits-footnote">Confirming records your explicit decision and unlocks the existing PayPal checkout flow. It does not independently verify the recipient or bypass spending limits.</p>
                  <div className="review-actions"><button disabled={ownReviewBusyId === item.id || !(reviewPasswords[item.id] || '').length} onClick={() => decideOwnReview(item, 'confirm')}>{ownReviewBusyId === item.id ? 'Verifying…' : 'Confirm payment'}</button><button disabled={ownReviewBusyId === item.id} onClick={() => decideOwnReview(item, 'reject')}>Reject payment</button></div>
                </> : <small className="review-resolution">{item.status === 'REVIEW_APPROVED' ? 'You confirmed this payment. Continue to PayPal from the payment screen when ready.' : item.status === 'BLOCK' ? 'PathGuard blocked this payment. It cannot be confirmed from this page.' : 'You rejected this payment. No PayPal order can be created.'}</small>}
              </div>;
            }) : <p className="muted">No payments have been flagged for review on your account. If PathGuard flags a payment, it will appear here.</p>}
          </div>
        </section> : activeTab === 'activity' ? <section className="tab-page">
          <div className="page-heading"><div className="eyebrow">PAYMENTS</div><h1>Activity</h1><p>Review your recent payment requests and their status.</p></div>
          <Transactions history={history} openPayment={(id) => { restorePayment(id); navigate('payments'); }} />
        </section> : activeTab === 'notifications' ? <section className="tab-page">
          <div className="page-heading"><div className="eyebrow">ACCOUNT UPDATES</div><h1>Notifications</h1><p>Recent payment and policy events from your account.</p></div>
          <div className="card info notifications-page"><h3><Bell /> Recent notifications <span className="queue-count">{notifications.length}</span></h3>
            {notifications.length ? notifications.map((item) => <div className="notification-item" key={item.id}><span className={`notification-dot ${item.severity}`}></span><div className="notification-content"><div className="notification-title-row"><b>{item.title}</b><span className={`incident-severity ${item.severity}`}>{item.severity}</span></div><p>{item.message}</p><small>{item.recipient} · {item.currency} {Number(item.amount).toLocaleString()} · {item.created_at ? new Date(item.created_at).toLocaleString() : ''}</small></div></div>) : <p className="muted">No recent notifications.</p>}
          </div>
        </section> : <>
        <section className="payment-workflow" style={{ display: activeTab === 'payments' ? undefined : 'none' }}>
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

          <div className="page-heading"><div className="eyebrow">CHECK FIRST. PAY SECOND.</div><h1>A thoughtful way to pay.</h1><p>Start with a few words. We’ll help you check the details.</p></div>
          <ol className="payment-stepper" aria-label="Payment progress">
            <li className={!payment ? 'current' : 'done'}><span>{payment ? <CheckCircle2 /> : '1'}</span><div><b>Describe</b><small>Who, how much, and why</small></div></li>
            <li className={payment && currentStatus !== 'COMPLETED' ? 'current' : currentStatus === 'COMPLETED' ? 'done' : ''}><span>{currentStatus === 'COMPLETED' ? <CheckCircle2 /> : '2'}</span><div><b>Check & review</b><small>Your safety decision</small></div></li>
            <li className={currentStatus === 'COMPLETED' ? 'done' : ''}><span>{currentStatus === 'COMPLETED' ? <CheckCircle2 /> : '3'}</span><div><b>PayPal checkout</b><small>Complete your payment</small></div></li>
          </ol>

          <div className="card composer">
            <div className="composer-heading"><div><span className="composer-icon"><Sparkles /></span><span><label>New payment request</label><small>Describe the payment in your own words</small></span></div><span className="secure-label"><LockKeyhole /> Private to your account</span></div>
            <textarea
              value={instruction}
              aria-label="Describe your payment"
              disabled={loading || payLoading}
              onChange={(e) => { setInstruction(e.target.value); setPayment(null); setError(''); setPaypalResult(null); }}
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
                  'Pay Alex $75 for consulting',
                ].map((x) => (
                  <button key={x} disabled={loading || payLoading} onClick={() => { setInstruction(x); setPayment(null); setPaypalResult(null); }}>{x}</button>
                ))}
              </div>

              <button
                className="primary"
                disabled={loading || payLoading || !instruction.trim()}
                onClick={analyze}
              >
                {loading ? (
                  <><Loader2 className="spin" /> Analyzing</>
                ) : (
                  <>Check payment <ArrowRight /></>
                )}
              </button>
            </div>
          </div>

          <div className="payment-reassurance"><ShieldCheck /><span>Your instruction creates a request. Money moves only after the required checks and checkout.</span><kbd>⌘ / Ctrl ↵</kbd></div>
          {!payment && !loading && <div className="payment-empty"><span><ShieldCheck /></span><h3>A clear picture before you pay.</h3><p>Your recipient, amount, risk signals, and next step will appear here after a check.</p></div>}
          {loading && <div className="analysis-loading" role="status"><Loader2 className="spin" /><div><b>Making sense of your payment…</b><p>Reading your instruction and checking your spending limits.</p></div></div>}
          {error && <div className="error" role="alert"><ShieldAlert /> <span>{error}</span></div>}

          {payment && (
            <Risk
              payment={payment}
              decision={decision}
              status={currentStatus}
              loading={payLoading}
              onPay={() => paypal(false)}
              onPayWithSavedWallet={() => paypal(true)}
              paypalConnected={paypalConnection.connected}
              onOpenReviews={() => setActiveTab('reviews')}
            />
          )}
        </section>

        <aside className="workspace-panels" style={{ display: ['security', 'wallet', 'intelligence'].includes(activeTab) ? undefined : 'none' }}>
          {activeTab !== 'overview' && <div className="page-heading panel-page-heading">
            <div className="eyebrow">{activeTab === 'wallet' ? 'CONNECTED ACCOUNTS' : activeTab === 'security' ? 'PAYMENT PROTECTION' : 'RISK & OPERATIONS'}</div>
            <h1>{activeTab === 'wallet' ? 'Payment methods' : activeTab === 'security' ? 'Security & limits' : 'Payment intelligence'}</h1>
            <p>{activeTab === 'wallet' ? 'Manage the PayPal Sandbox wallet connected to your account.' : activeTab === 'security' ? 'Control your spending boundaries and see how much capacity remains.' : 'Understand payment outcomes, recurring signals, and recommended actions.'}</p>
          </div>}
          <div className="card info limits-card paypal-connection-card" style={{ display: activeTab === 'wallet' ? undefined : 'none' }}>
            <div className="wallet-banner"><span className="wallet-monogram">P</span><span>PAYMENT PROVIDER</span><b>PayPal</b><small>Sandbox wallet</small></div><h3><Link2 /> Your connected wallet</h3>
            {paypalConnection.connected ? (
              <>
                <div className="paypal-connection-state">
                  <CheckCircle2 />
                  <div>
                    <b>Sandbox wallet connected</b>
                    <small>{paypalConnection.email_address || 'Your PayPal wallet is linked to this PathGuard account.'}</small>
                  </div>
                </div>
                <p className="limits-intro">Your wallet is linked. "Continue with PayPal" still opens PayPal Checkout for approval; the payment review also offers a separate saved-wallet option for quicker checkout.</p>
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

          <div className="card info limits-card spending-limits-panel" style={{ display: activeTab === 'security' ? undefined : 'none' }}>
            <div className="section-intro"><span className="section-icon"><ShieldCheck /></span><div><h2>Your boundaries. Your control.</h2><p>Set limits that work for you.</p></div></div><h3><Settings2 /> Spending limits</h3>
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

          <div className="card info intelligence-panel" style={{ display: activeTab === 'intelligence' ? undefined : 'none' }}>
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

          {['reviewer', 'admin'].includes(user.role) && activeTab === 'intelligence' && <div className="card info">
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

      <footer><span><ShieldCheck /> PathGuard Pay</span><span>Intent. Clarity. Checkout.</span><span>Sandbox environment · No real money</span></footer>
    </>
  );
}

function Brand({ compact = false }) {
  return <div className={`brand ${compact ? 'compact' : ''}`}><span className="logo"><ShieldCheck /></span><div><b>PathGuard<span> Pay</span></b><small>Clarity before checkout</small></div></div>;
}

const money = (value) => Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function EmptyState({ icon: Icon = History, title, description, action }) {
  return <div className="empty-state"><span><Icon /></span><h3>{title}</h3><p>{description}</p>{action}</div>;
}

function Overview({ user, history, overview, limits, reviews, navigate, openPayment }) {
  const pending = reviews.filter(item => item.status === 'REVIEW_PENDING').length;
  const total = overview?.total_payments;
  const blocked = overview?.blocked_payments;
  const remaining = limits?.daily_remaining;
  const ratio = limits?.daily_limit ? Math.min(100, Math.max(0, Number(limits.daily_used || 0) / limits.daily_limit * 100)) : 0;
  const metrics = [
    ['Completed spend', overview ? `$${money(overview.completed_spend_usd)}` : '—', CircleDollarSign, 'Completed payments only'],
    ['Payment checks', total == null ? '—' : total.toLocaleString(), ShieldCheck, 'Requests checked before checkout'],
    ['Needs your review', pending, ClipboardCheck, pending ? 'Your decision is needed' : 'Nothing waiting on you'],
    ['Blocked requests', blocked == null ? '—' : blocked.toLocaleString(), ShieldX, 'Stopped by payment checks'],
  ];
  return <section className="overview-page">
    <div className="dashboard-heading"><div><div className="eyebrow">YOUR PAYMENT WORKSPACE</div><h1>Hello, {user.display_name?.split(' ')[0] || 'there'}<span className="heading-dot">.</span></h1><p>A clearer view of your payments. A little more peace of mind.</p></div><button className="primary" onClick={() => navigate('payments')}><Plus /> New payment</button></div>
    <div className="metric-grid">{metrics.map(([label, value, Icon, note], index) => <div className={`metric-card metric-${index}`} key={label}><div className="metric-label"><span>{label}</span><Icon /></div><strong>{value}</strong><small>{index === 2 && pending > 0 ? <span className="attention-dot" /> : null}{note}</small></div>)}</div>
    {overview?.scope === 'organization' && <p className="scope-note">Spend, checks, and blocks cover the organization. Reviews and recent activity below belong to your account.</p>}
    <div className="overview-grid">
      <div className="overview-primary">
        <div className="clarity-card"><div className="clarity-copy"><span className="eyebrow"><Sparkles /> A BETTER MOMENT TO CHECK</span><h2>Big plans.<br />Thoughtful payments.</h2><p>Describe what you want to pay. Check the details and risk signals before you continue.</p><button className="text-action" onClick={() => navigate('payments')}>Make your next payment <ArrowUpRight /></button></div><div className="clarity-art" aria-hidden="true"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><span className="shield-tile"><ShieldCheck /></span><span className="orbit-chip"><CheckCircle2 /> Check first</span></div></div>
        <div className="card recent-card"><div className="section-heading"><div><h2>Recent activity</h2><p>Your latest payment requests, at a glance.</p></div><button className="text-action" onClick={() => navigate('activity')}>View all <ArrowUpRight /></button></div>
          {history.length ? <div className="recent-list">{history.slice(0,5).map(item => <PaymentRow key={item.id} item={item} onClick={() => openPayment(item.id)} />)}</div> : <EmptyState title="Your story starts here." description="Check your first payment and its progress will appear here." action={<button className="secondary" onClick={() => navigate('payments')}>Create a payment <ArrowRight /></button>} />}
        </div>
      </div>
      <div className="overview-secondary">
        <div className="card budget-card"><div className="section-heading"><h2>Room to pay</h2><span className="mini-label">TODAY · USD</span></div><div className="budget-ring" style={{'--used': `${ratio}%`}}><div><span>Available today</span><strong>{!limits ? '—' : remaining == null ? 'No daily cap' : `$${money(remaining)}`}</strong><small>{limits?.timezone?.replaceAll('_',' ') || 'Your spending limits'}</small></div></div><div className="budget-legend"><span><i /> Used or reserved</span><b>{limits ? `$${money(limits.daily_used)}` : '—'}</b></div><div className="budget-legend"><span><i /> Daily limit</span><b>{!limits ? '—' : limits.daily_limit == null ? 'No cap' : `$${money(limits.daily_limit)}`}</b></div><button className="secondary" onClick={() => navigate('security')}><Settings2 /> Manage spending limits</button></div>
        <div className={`card attention-card ${pending ? 'has-pending' : ''}`}><div className="attention-icon">{pending ? <ClipboardCheck /> : <CheckCircle2 />}</div><h2>{pending ? `${pending} payment${pending > 1 ? 's' : ''} to review` : 'You’re all caught up.'}</h2><p>{pending ? 'Take a moment to review the details before deciding what happens next.' : 'No payment requests are waiting for your confirmation.'}</p><button className="text-action" onClick={() => navigate('reviews')}>{pending ? 'Review payments' : 'View payment reviews'} <ArrowRight /></button></div>
        <div className="sandbox-note"><LockKeyhole /><p><b>A space to try things.</b>This workspace uses PayPal Sandbox. No real money is moved.</p></div>
      </div>
    </div>
  </section>;
}

function PaymentRow({ item, onClick }) {
  const meta = statusMeta(item.status);
  return <button className="payment-row" onClick={onClick} aria-label={`View payment to ${item.recipient}, ${item.currency} ${money(item.amount)}, ${meta.label}`}><span className={`payment-avatar ${meta.tone}`}>{(item.recipient || '?').slice(0,1).toUpperCase()}</span><span className="payment-person"><b>{item.recipient}</b><small>{item.purpose || 'Payment request'}</small></span><span className="payment-date">{item.created_at ? new Date(item.created_at).toLocaleDateString(undefined,{month:'short',day:'numeric'}) : '—'}</span><span className={`status-pill ${meta.tone}`}>{meta.icon}{meta.label}</span><span className="payment-amount"><b>{item.currency} {money(item.amount)}</b><small>Payment request</small></span><ChevronRight className="row-chevron" /></button>;
}

function Transactions({ history, openPayment }) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const filtered = history.filter(item => [item.recipient,item.purpose,item.status].filter(Boolean).join(' ').toLowerCase().includes(query.toLowerCase()) && (filter === 'all' || (filter === 'completed' ? item.status === 'COMPLETED' : filter === 'review' ? ['REVIEW_PENDING','REVIEW_APPROVED'].includes(item.status) : ['BLOCK','REVIEW_REJECTED'].includes(item.status))));
  return <div className="card transactions-card"><div className="transaction-toolbar"><div className="filter-tabs" aria-label="Filter transactions">{[['all','All activity'],['completed','Completed'],['review','In review'],['blocked','Stopped']].map(([value,label]) => <button key={value} aria-pressed={filter === value} className={filter === value ? 'selected' : ''} onClick={() => setFilter(value)}>{label}</button>)}</div><label className="search-field"><Search /><input aria-label="Search transactions" placeholder="Search transactions…" value={query} onChange={event => setQuery(event.target.value)} /></label></div><div className="transaction-labels"><span>RECIPIENT / PURPOSE</span><span>DATE</span><span>STATUS</span><span>AMOUNT</span></div>{filtered.length ? filtered.map(item => <PaymentRow key={item.id} item={item} onClick={() => openPayment(item.id)} />) : <EmptyState icon={query || filter !== 'all' ? Search : History} title={history.length ? 'No matching payments.' : 'No payments just yet.'} description={history.length ? 'Try a different search or activity filter.' : 'Your payment requests and their progress will appear here.'} />}<div className="table-footer">Showing {filtered.length} of {history.length} recent requests</div></div>;
}

function RecipientProfile({ profile, currency }) {
  if (!profile) {
    return (
      <div className="recipient-profile recipient-profile-loading">
        <div className="recipient-profile-heading"><ShieldCheck /><span><b>Recipient trust profile</b><small>Loading your payment history…</small></span></div>
      </div>
    );
  }

  const established = profile.trust_level === 'ESTABLISHED';
  const developing = profile.trust_level === 'DEVELOPING';
  const trustLabel = established ? 'Established history' : developing ? 'Developing history' : 'New recipient';
  const average = Number(profile.average_amount || 0);
  const recentAverage = profile.recent_average_amount == null ? null : Number(profile.recent_average_amount);
  const lastPayment = profile.last_payment_at ? new Date(profile.last_payment_at).toLocaleDateString() : null;

  return (
    <div className="recipient-profile">
      <div className="recipient-profile-heading">
        <span className={`recipient-trust-icon ${established ? 'established' : developing ? 'developing' : 'new'}`}>
          {established ? <ShieldCheck /> : developing ? <Activity /> : <ShieldAlert />}
        </span>
        <span className="recipient-trust-copy"><b>Recipient trust profile</b><small>Based on your completed payments in this currency</small></span>
        <span className={`recipient-trust-badge ${established ? 'established' : developing ? 'developing' : 'new'}`}>{trustLabel}</span>
      </div>

      {profile.total_payments > 0 ? (
        <>
          <div className="recipient-profile-stats">
            <div><small>COMPLETED PAYMENTS</small><b>{profile.total_payments}</b></div>
            <div><small>AVERAGE AMOUNT</small><b>{currency} {average.toLocaleString(undefined, { maximumFractionDigits: 2 })}</b></div>
            <div><small>LAST PAYMENT</small><b>{lastPayment || '—'}</b></div>
          </div>
          <div className="recipient-profile-range">
            <span>Historical range</span>
            <b>{currency} {Number(profile.minimum_amount || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })} – {Number(profile.maximum_amount || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}</b>
          </div>
          <div className="recipient-profile-range">
            <span>Last 30 days</span>
            <b>{profile.recent_payments} payment(s){recentAverage == null ? '' : ` · ${currency} ${recentAverage.toLocaleString(undefined, { maximumFractionDigits: 2 })} average`}</b>
          </div>
        </>
      ) : (
        <p className="recipient-profile-empty">No completed payments to this recipient are recorded on your account yet. PathGuard treats this as a new-recipient signal, not proof of fraud.</p>
      )}
      <small className="recipient-profile-footnote">Trust labels describe payment history only. They do not verify the recipient’s real-world identity or guarantee a safe payment.</small>
    </div>
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


function formatAdminMoney(value) {
  return Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatAdminDate(value) {
  return value ? new Date(value).toLocaleDateString() : '—';
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
        if (response.status === 401 || response.status === 403) {
          throw new Error('Administrator access is required. Sign in with an active admin account.');
        }
        if (!response.ok) throw new Error('Could not load administrator data.');
      }
      const [overviewData, usersData, paymentsData] = await Promise.all(responses.map(response => response.json()));
      setOverview(overviewData);
      setUsers(usersData.items || []);
      setPayments(paymentsData.items || []);
    } catch (err) {
      setError(err.message || 'Could not load administrator data.');
    }
  }

  useEffect(() => { refresh(); }, []);

  async function searchUsers(event) {
    event?.preventDefault();
    setError('');
    try {
      const response = await apiFetch(API + '/api/admin/users?limit=100&q=' + encodeURIComponent(query.trim()));
      if (!response.ok) throw new Error(response.status === 403 ? 'Administrator access is required.' : 'Could not search users.');
      const data = await response.json();
      setUsers(data.items || []);
    } catch (err) {
      setError(err.message || 'Could not search users.');
    }
  }

  async function updateUser(account, changes) {
    setBusyId(account.id);
    setError('');
    setNotice('');
    try {
      const response = await apiFetch(API + '/api/admin/users/' + account.id, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(changes),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not update this account.');
      setNotice('Updated ' + data.email + '.');
      await refresh();
      if (query.trim()) await searchUsers();
    } catch (err) {
      setError(err.message || 'Could not update this account.');
    } finally {
      setBusyId(null);
    }
  }

  const visiblePayments = payments.filter(item =>
    [item.user_email, item.recipient, item.status, item.purpose, String(item.id)]
      .filter(Boolean).join(' ').toLowerCase().includes(paymentQuery.toLowerCase())
  );

  return <section className="tab-page admin-page">
    <div className="page-heading admin-heading">
      <div><div className="eyebrow">PLATFORM CONTROL</div><h1>Admin dashboard</h1><p>Manage accounts and monitor platform-wide payment activity.</p></div>
      <button className="admin-refresh" onClick={refresh}><RefreshCw /> Refresh data</button>
    </div>
    {error && <div className="error"><ShieldAlert /><span>{error}</span></div>}
    {notice && <div className="admin-notice"><CheckCircle2 />{notice}</div>}
    <div className="admin-metrics">
      {[
        ['Registered users', overview?.users_total, Users],
        ['Active users', overview?.active_users, CheckCircle2],
        ['All payments', overview?.payments_total, History],
        ['Completed volume', '$' + formatAdminMoney(overview?.completed_payment_volume), CircleDollarSign],
        ['Blocked', overview?.blocked_payments, ShieldX],
        ['Pending', overview?.pending_payments, Clock3],
      ].map(([label, value, Icon]) => <div className="card admin-metric" key={label}><span><Icon /></span><small>{label}</small><b>{value ?? '—'}</b></div>)}
    </div>
    <div className="admin-switch">
      <button className={view === 'users' ? 'selected' : ''} onClick={() => setView('users')}><Users /> User management</button>
      <button className={view === 'payments' ? 'selected' : ''} onClick={() => setView('payments')}><History /> All payments</button>
    </div>
    {view === 'users' ? <div className="card admin-table-card">
      <div className="admin-table-heading">
        <div><h2>Users</h2><p>Search accounts, review roles, and manage access.</p></div>
        <form className="admin-search" onSubmit={searchUsers}><Search /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search name or email" /><button type="submit">Search</button></form>
      </div>
      <div className="admin-table-scroll"><table className="admin-table"><thead><tr><th>User</th><th>Role</th><th>Payments</th><th>Joined</th><th>Status</th><th>Actions</th></tr></thead>
        <tbody>{users.map(account => <tr key={account.id}>
          <td><b>{account.display_name}</b><small>{account.email}</small><small>Account #{account.id}</small></td>
          <td><select aria-label={'Role for ' + account.email} value={account.role} disabled={busyId === account.id} onChange={event => updateUser(account, { role: event.target.value })}><option value="customer">Customer</option><option value="reviewer">Reviewer</option><option value="admin">Admin</option></select></td>
          <td>{account.payment_count}</td><td>{formatAdminDate(account.created_at)}</td>
          <td><span className={'admin-state ' + (account.is_active ? 'active' : 'inactive')}>{account.is_active ? 'Active' : 'Inactive'}</span></td>
          <td><button className={'admin-action ' + (account.is_active ? 'deactivate' : 'activate')} disabled={busyId === account.id} onClick={() => updateUser(account, { is_active: !account.is_active })}>{busyId === account.id ? 'Saving…' : account.is_active ? 'Deactivate' : 'Reactivate'}</button></td>
        </tr>)}</tbody></table>
        {!users.length && <p className="muted admin-empty">No users match this search.</p>}
      </div>
    </div> : <div className="card admin-table-card">
      <div className="admin-table-heading"><div><h2>All payments</h2><p>Platform-wide payment activity and risk decisions.</p></div><div className="admin-search"><Search /><input value={paymentQuery} onChange={event => setPaymentQuery(event.target.value)} placeholder="Search payment, user, status" /></div></div>
      <div className="admin-table-scroll"><table className="admin-table"><thead><tr><th>Payment</th><th>Account</th><th>Amount</th><th>Risk</th><th>Status</th><th>Created</th></tr></thead>
        <tbody>{visiblePayments.map(item => <tr key={item.id}>
          <td><b>#{item.id} · {item.recipient}</b><small>{item.purpose || 'Payment'}</small></td><td>{item.user_email}</td>
          <td>{item.currency} {formatAdminMoney(item.amount)}</td><td>{item.risk_score ?? '—'}{item.risk_decision ? <small>{item.risk_decision}</small> : null}</td>
          <td><span className={'admin-state ' + (item.status === 'COMPLETED' ? 'active' : item.status === 'BLOCK' ? 'inactive' : 'pending')}>{item.status}</span></td><td>{formatAdminDate(item.created_at)}</td>
        </tr>)}</tbody></table>
        {!visiblePayments.length && <p className="muted admin-empty">No payments match this search.</p>}
      </div>
    </div>}
    <p className="admin-footnote">Sensitive account controls are available only to administrators. Changes are enforced by the backend.</p>
  </section>;
}

function Risk({ payment, decision, status, loading, onPay, onPayWithSavedWallet, paypalConnected, onOpenReviews }) {
  const decisionConfig = {
    ALLOW: ['allow', <CheckCircle2 />, 'Ready for your review'],
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
  if (status === 'REVIEW_PENDING') message = 'Open Payment Reviews to confirm or reject this payment before PayPal checkout.';
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
          <span className="score-label">RISK SCORE</span><b>{payment?.risk?.risk_score ?? 0}</b><small>/100</small>
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

      <RecipientProfile profile={payment?.recipient_profile} currency={payment?.intent?.currency || 'USD'} />

      <div className="reasons">
        <b><ShieldAlert /> Why PathGuard decided this</b>
        {reasons.length
          ? reasons.map((r, i) => <p key={`${r}-${i}`}><span className="reason-marker">{decision === 'ALLOW' ? <CheckCircle2 /> : <ShieldAlert />}</span>{r}</p>)
          : <p>No additional risk reasons were reported.</p>}
      </div>

      {decision === 'BLOCK' ? (
        <div className="blocked"><ShieldX /> {payment?.paypal ? 'Payment blocked before capture. PathGuard did not capture the existing PayPal order.' : 'No PayPal order was created.'}</div>
      ) : status === 'REVIEW_REJECTED' ? (
        <div className="blocked review-rejected"><ShieldX /> This payment was rejected during human review.</div>
      ) : status === 'REVIEW_PENDING' ? (
        <div className="blocked review-held"><Clock3 /> This payment needs your decision. Open Payment Reviews to continue.
          <button className="review-open-button" onClick={onOpenReviews}>Open Payment Reviews <ArrowRight /></button>
        </div>
      ) : status === 'COMPLETED' ? (
        <div className="completed-inline"><CheckCircle2 /> Payment captured successfully.</div>
      ) : status === 'PAYPAL_PENDING_APPROVAL' ? (
        <div className="blocked paypal-held"><Clock3 /> PayPal checkout is awaiting approval.</div>
      ) : status === 'PAYPAL_PENDING_CAPTURE' ? (
        <div className="blocked paypal-held"><Loader2 className="spin" /> PayPal approved. Capture is in progress.</div>
      ) : canPay ? (
        <>
          <button className="paypal" disabled={loading} onClick={onPay}>
            {loading
              ? <><Loader2 className="spin" /> Creating PayPal order…</>
              : <>Continue with PayPal <ArrowRight /></>}
          </button>
          {paypalConnected && (
            <button className="paypal saved-paypal" disabled={loading} onClick={onPayWithSavedWallet}>
              {loading
                ? <><Loader2 className="spin" /> Processing payment…</>
                : <>Pay with saved PayPal wallet <ShieldCheck /></>}
            </button>
          )}
        </>
      ) : null}
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);

