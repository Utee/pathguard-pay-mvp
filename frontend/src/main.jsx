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
} from 'lucide-react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

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
  const [instruction, setInstruction] = useState('');
  const [payment, setPayment] = useState(null);
  const [history, setHistory] = useState([]);
  const [reviewQueue, setReviewQueue] = useState([]);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [payLoading, setPayLoading] = useState(false);
  const [error, setError] = useState('');
  const [paypalResult, setPaypalResult] = useState(null);

  async function load() {
    try {
      const r = await fetch(`${API}/api/payments`);
      if (r.ok) setHistory(await r.json());

      const reviews = await fetch(`${API}/api/reviews`);
      if (reviews.ok) setReviewQueue(await reviews.json());
    } catch {
      // Keep the dashboard usable if history is temporarily unavailable.
    }
  }

  async function restorePayment(paymentId) {
    if (!paymentId) return;

    try {
      const r = await fetch(`${API}/api/payments/${paymentId}`);
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
    load();

    const q = new URLSearchParams(window.location.search);
    const paypalState = q.get('paypal');
    const paypalToken = q.get('token');
    const paymentId = q.get('payment_id');
    const orderId = q.get('order_id');
    const captureId = q.get('capture_id');
    const message = q.get('message');
    const approvalUrl = q.get('approval_url');

    const savedPaymentId = localStorage.getItem('pathguard_paypal_payment_id');
    const effectivePaymentId = paymentId || savedPaymentId;

    async function syncReturnedPayment(token) {
      if (!token) return null;

      try {
        const r = await fetch(
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
        const current = await fetch(`${API}/api/payments/${effectivePaymentId}`);
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

      load();
      localStorage.removeItem('pathguard_paypal_payment_id');
    }

    restoreAfterPayPalReturn();

    window.history.replaceState({}, '', window.location.pathname);
  }, []);

  async function decideReview(item, action) {
    setReviewLoading(true);
    setError('');

    try {
      const r = await fetch(`${API}/api/reviews/${item.id}/${action}`, {
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

  async function analyze() {
    if (!instruction.trim()) return;

    setLoading(true);
    setError('');
    setPaypalResult(null);
    setPayment(null);

    try {
      const r = await fetch(`${API}/api/payments/analyze`, {
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
      const r = await fetch(
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

      if (d.approval_url) {
        localStorage.setItem('pathguard_paypal_payment_id', String(payment.payment_id));
        window.location.href = d.approval_url;
      } else {
        throw new Error('No PayPal approval URL returned');
      }
    } catch (e) {
      setError(e.message || 'PayPal order failed');
      setPayLoading(false);
    }
  }

  const risk = payment?.risk;
  const decision = risk?.decision;
  const currentStatus = payment?.status || decision;

  return (
    <>
      <header>
        <div className="brand">
          <div className="logo"><ShieldCheck /></div>
          <div>
            <b>PathGuard Pay</b>
            <small>AI payment safety layer</small>
          </div>
        </div>
        <span className="sandbox">● PayPal Sandbox</span>
      </header>

      <main>
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

          <div className="eyebrow">AI PAYMENT AGENT</div>
          <h1>Think before the AI pays.</h1>
          <p className="intro">
            Tell the payment agent what you want to pay. PathGuard checks the intent
            and transaction risk before PayPal moves the money.
          </p>

          <div className="card composer">
            <label>What would you like to pay?</label>
            <textarea
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder={'Try: "Pay John $200 for the website"'}
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
          <div className="card info">
            <h3><ShieldCheck /> How PathGuard works</h3>
            <Step n="01" t="Understand" d="AI turns your request into structured payment intent." />
            <Step n="02" t="Check" d="PathGuard evaluates recipient and amount risk." />
            <Step n="03" t="Decide" d="The payment gets Allow, Review, or Block." />
            <Step n="04" t="Pay" d="Only approved payments continue to PayPal." />
          </div>

          <div className="card info">
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
          </div>

          <div className="card info">
            <h3><History /> Recent activity</h3>
            {history.length ? (
              history.slice(0, 7).map((x) => {
                const meta = statusMeta(x.status);
                return (
                  <div className="row" key={x.id}>
                    <div className={`status ${meta.tone}`}>{meta.icon}</div>
                    <div>
                      <b>{x.recipient}</b>
                      <small>{x.purpose || 'Payment'}</small>
                      <span className="activity-status">{meta.label}</span>
                    </div>
                    <strong>{x.currency} {Number(x.amount).toLocaleString()}</strong>
                  </div>
                );
              })
            ) : (
              <p className="muted">Your payment activity will appear here.</p>
            )}
          </div>
        </aside>
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
        <div className="blocked"><ShieldX /> No PayPal order was created.</div>
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
