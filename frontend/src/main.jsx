import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
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
} from 'lucide-react';
import './styles.css';

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

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

  useEffect(() => {
    load();

    const q = new URLSearchParams(window.location.search);
    const paypalState = q.get('paypal');
    const paymentId = q.get('payment_id');
    const orderId = q.get('order_id');
    const captureId = q.get('capture_id');
    const message = q.get('message');

    if (!paypalState) return;

    setPaypalResult({
      state: paypalState,
      paymentId,
      orderId,
      captureId,
      message,
    });

    async function restorePayment() {
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
          });
        }
      } catch {
        // The payment result banner is still useful even if the detail request fails.
      }
    }

    restorePayment();
    load();

    // Remove PayPal query parameters after reading them so refreshing the page
    // does not repeat the return-state handling.
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
      setHistory((items) => items.map((x) => x.id === item.id ? { ...x, status: d.status } : x));
      setPayment((current) => current?.payment_id === item.id
        ? { ...current, status: d.status }
        : current);
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
        status: d.risk?.decision === 'REVIEW' ? 'REVIEW_PENDING' : d.risk?.decision,
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

      if (d.approval_url) {
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

  return (
    <>
      <header>
        <div className="brand">
          <div className="logo">
            <ShieldCheck />
          </div>
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
            <div className="success">
              <PartyPopper />
              <div>
                <b>Payment completed successfully.</b>
                <small>PayPal Sandbox has captured the payment.</small>
                {paypalResult.orderId && (
                  <small>Order ID: {paypalResult.orderId}</small>
                )}
                {paypalResult.captureId && (
                  <small>Capture ID: {paypalResult.captureId}</small>
                )}
              </div>
            </div>
          )}

          {paypalResult?.state === 'approved' && (
            <div className="success">
              <CheckCircle2 />
              <div>
                <b>Payment approved by PayPal.</b>
                <small>Waiting for the server to finish capture.</small>
                {paypalResult.orderId && (
                  <small>Order ID: {paypalResult.orderId}</small>
                )}
              </div>
            </div>
          )}

          {paypalResult?.state === 'pending' && (
            <div className="notice">
              <Clock3 />
              <div>
                <b>Payment is still processing.</b>
                <small>
                  PayPal approved the order, but the capture has not completed yet.
                </small>
              </div>
            </div>
          )}

          {paypalResult?.state === 'cancelled' && (
            <div className="notice">
              <Clock3 />
              <div>
                <b>PayPal checkout was cancelled.</b>
                <small>No payment was captured.</small>
              </div>
            </div>
          )}

          {paypalResult?.state === 'error' && (
            <div className="error">
              <ShieldAlert />
              <div>
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
                  <button key={x} onClick={() => setInstruction(x)}>
                    {x}
                  </button>
                ))}
              </div>

              <button
                className="primary"
                disabled={loading || !instruction.trim()}
                onClick={analyze}
              >
                {loading ? (
                  <>
                    <Loader2 className="spin" />
                    Analyzing
                  </>
                ) : (
                  <>
                    Analyze payment <ArrowRight />
                  </>
                )}
              </button>
            </div>
          </div>

          {error && <div className="error">{error}</div>}

          {payment && (
            <Risk
              payment={payment}
              decision={decision}
              loading={payLoading}
              onPay={paypal}
            />
          )}
        </section>

        <aside>
          <div className="card info">
            <h3>
              <ShieldCheck /> How PathGuard works
            </h3>
            <Step
              n="01"
              t="Understand"
              d="AI turns your request into structured payment intent."
            />
            <Step
              n="02"
              t="Check"
              d="PathGuard evaluates recipient and amount risk."
            />
            <Step
              n="03"
              t="Decide"
              d="The payment gets Allow, Review, or Block."
            />
            <Step
              n="04"
              t="Pay"
              d="Only approved payments continue to PayPal."
            />
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
            <h3>
              <History /> Recent activity
            </h3>

            {history.length ? (
              history.slice(0, 7).map((x) => (
                <div className="row" key={x.id}>
                  <div className={`status ${x.status}`}>
                    {x.status === 'BLOCK' ? (
                      <ShieldX />
                    ) : x.status === 'ALLOW' || x.status === 'COMPLETED' ? (
                      <CheckCircle2 />
                    ) : (
                      <Clock3 />
                    )}
                  </div>
                  <div>
                    <b>{x.recipient}</b>
                    <small>{x.purpose || 'Payment'}</small>
                  </div>
                  <strong>
                    {x.currency} {Number(x.amount).toLocaleString()}
                  </strong>
                </div>
              ))
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
      <div>
        <b>{t}</b>
        <small>{d}</small>
      </div>
    </div>
  );
}

function Risk({ payment, decision, loading, onPay }) {
  const config = {
    ALLOW: ['allow', <CheckCircle2 />, 'Payment approved'],
    REVIEW: ['review', <Clock3 />, 'Payment needs review'],
    BLOCK: ['block', <ShieldX />, 'Payment blocked'],
  };

  const cfg =
    config[decision] || ['review', <ShieldAlert />, 'Payment result'];

  const reasons = Array.isArray(payment?.risk?.reasons)
    ? payment.risk.reasons
    : [];

  const amount = Number(payment?.intent?.amount || 0);

  return (
    <div className={`card risk ${cfg[0]}`}>
      <div className="riskhead">
        <div className="riskicon">{cfg[1]}</div>
        <div>
          <small>PATHGUARD DECISION</small>
          <h2>{cfg[2]}</h2>
          <p>
            {decision === 'BLOCK'
              ? 'PathGuard stopped this payment before PayPal execution.'
              : 'Review the payment details before continuing.'}
          </p>
        </div>
        <div className="score">
          <b>{payment?.risk?.risk_score ?? 0}</b>
          <small>/100</small>
        </div>
      </div>

      <div className="summary">
        <div>
          <small>RECIPIENT</small>
          <b>{payment?.intent?.recipient_name || 'Unknown'}</b>
        </div>
        <div>
          <small>AMOUNT</small>
          <b>
            {payment?.intent?.currency || 'USD'} {amount.toLocaleString()}
          </b>
        </div>
        <div>
          <small>PURPOSE</small>
          <b>{payment?.intent?.purpose || 'Payment'}</b>
        </div>
      </div>

      <div className="reasons">
        <b>
          <ShieldAlert /> Why PathGuard decided this
        </b>
        {reasons.length ? (
          reasons.map((r, i) => <p key={`${r}-${i}`}>✓ {r}</p>)
        ) : (
          <p>✓ No additional risk reasons were reported.</p>
        )}
      </div>

      {decision === 'BLOCK' ? (
        <div className="blocked">
          <ShieldX /> No PayPal order was created.
        </div>
      ) : decision === 'REVIEW' && payment?.status !== 'REVIEW_APPROVED' ? (
        <div className="blocked review-held">
          <Clock3 /> This payment is on hold until a reviewer approves it.
        </div>
      ) : decision === 'REVIEW' && payment?.status === 'REVIEW_APPROVED' ? (
        <button className="paypal" disabled={loading} onClick={onPay}>
          {loading ? (
            <>
              <Loader2 className="spin" />
              Creating PayPal order…
            </>
          ) : (
            <>
              Continue with PayPal <ArrowRight />
            </>
          )}
        </button>
      ) : (
        <button className="paypal" disabled={loading} onClick={onPay}>
          {loading ? <><Loader2 className="spin" /> Creating PayPal order…</> : <>Continue with PayPal <ArrowRight /></>}
        </button>
      )}
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
