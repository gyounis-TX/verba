import { useNavigate } from "react-router-dom";
import { Link } from "react-router-dom";
import "./LandingPage.css";

const HOW_IT_WORKS = [
  {
    step: "1",
    title: "Upload or paste your report",
    desc: "Drop a PDF, snap a photo, or paste text from any medical report.",
  },
  {
    step: "2",
    title: "Add clinical context",
    desc: "Add a one-liner or paste the last progress note to personalize the explanation.",
  },
  {
    step: "3",
    title: "AI identifies the test type",
    desc: "Automatically detects labs, imaging, cardiac tests, and 40+ more.",
  },
  {
    step: "4",
    title: "Get a clear explanation",
    desc: "Receive a jargon-free summary tailored to your patient's reading level.",
  },
  {
    step: "5",
    title: "Share with your patient",
    desc: "Paste directly into your EHR or send as a message to your patient.",
  },
];

const FEATURES = [
  { title: "40+ Test Types", desc: "Labs, echo, stress, PET/CT, MRI, CT, X-ray, and more" },
  { title: "Clinical Context", desc: "The more context you provide, the more personalized the response. Add a one-liner or paste the last progress note." },
  { title: "Tailored Responses", desc: "Sliders to tailor every response by education level, detail, level of concern, and patient anxiety." },
  { title: "Teaching Points", desc: "Teach Explify how you want specific results interpreted or conveyed to patients." },
  { title: "Continuously Improving", desc: "By tracking which responses you like and why, as well as edits you make, Explify learns your style over time." },
  { title: "Custom Templates", desc: "Save and reuse your preferred explanation formats for any given test type." },
];

export function LandingPage() {
  const navigate = useNavigate();

  const scrollToPricing = () => {
    document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className="landing">
      {/* Nav */}
      <header className="landing-nav">
        <span className="landing-nav-brand">Explify</span>
        <div className="landing-nav-actions">
          <button className="landing-nav-signin" onClick={() => navigate("/auth")}>
            Sign In
          </button>
          <button className="landing-nav-cta" onClick={() => navigate("/auth")}>
            Try Free
          </button>
        </div>
      </header>

      {/* Hero */}
      <section className="landing-hero">
        <h1 className="landing-hero-title">
          Explain Any Medical Report in Seconds
        </h1>
        <p className="landing-hero-subtitle">
          AI-powered explanations that make lab results, imaging, and cardiac tests
          clear for your patients. Save hours of typing, deliver better care.
        </p>
        <div className="landing-hero-actions">
          <button className="landing-btn-primary" onClick={() => navigate("/auth")}>
            Try Free for 14 Days
          </button>
          <button className="landing-btn-secondary" onClick={scrollToPricing}>
            See Pricing
          </button>
        </div>
      </section>

      {/* How It Works */}
      <section className="landing-section">
        <h2 className="landing-section-title">How It Works</h2>
        <div className="landing-steps">
          {HOW_IT_WORKS.map((item) => (
            <div key={item.step} className="landing-step">
              <span className="landing-step-number">{item.step}</span>
              <h3 className="landing-step-title">{item.title}</h3>
              <p className="landing-step-desc">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="landing-section landing-section--alt">
        <h2 className="landing-section-title">Built for Busy Physicians</h2>
        <div className="landing-features">
          {FEATURES.map((f) => (
            <div key={f.title} className="landing-feature">
              <h3 className="landing-feature-title">{f.title}</h3>
              <p className="landing-feature-desc">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Pricing */}
      <section className="landing-section" id="pricing">
        <h2 className="landing-section-title">Simple, Transparent Pricing</h2>
        <p className="landing-section-subtitle">
          Start with a free 14-day trial. No credit card required.
        </p>
        <div className="landing-pricing">
          <div className="landing-price-card">
            <h3 className="landing-price-tier">Starter</h3>
            <div className="landing-price-amount">
              <span className="landing-price-dollar">$29</span>
              <span className="landing-price-period">/month</span>
            </div>
            <ul className="landing-price-features">
              <li>75 reports/month</li>
              <li>All test types</li>
              <li>30-day history</li>
            </ul>
            <button className="landing-btn-primary" onClick={() => navigate("/auth?plan=starter")}>
              Start Free Trial
            </button>
          </div>

          <div className="landing-price-card landing-price-card--popular">
            <span className="landing-price-badge">Most Popular</span>
            <h3 className="landing-price-tier">Professional</h3>
            <div className="landing-price-amount">
              <span className="landing-price-dollar">$49</span>
              <span className="landing-price-period">/month</span>
            </div>
            <ul className="landing-price-features">
              <li>300 reports/month</li>
              <li>Deep analysis &amp; trends</li>
              <li>Patient letters</li>
              <li>Custom templates</li>
              <li>Batch processing (up to 3)</li>
              <li>Unlimited history</li>
            </ul>
            <button className="landing-btn-primary" onClick={() => navigate("/auth?plan=professional")}>
              Start Free Trial
            </button>
          </div>

          <div className="landing-price-card">
            <h3 className="landing-price-tier">Unlimited</h3>
            <div className="landing-price-amount">
              <span className="landing-price-dollar">$99</span>
              <span className="landing-price-period">/month</span>
            </div>
            <ul className="landing-price-features">
              <li>Unlimited reports</li>
              <li>Everything in Professional</li>
              <li>Batch processing (up to 10)</li>
              <li>Priority support</li>
            </ul>
            <button className="landing-btn-primary" onClick={() => navigate("/auth?plan=unlimited")}>
              Start Free Trial
            </button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="landing-footer">
        <div className="landing-footer-links">
          <Link to="/terms">Terms of Service</Link>
          <Link to="/privacy">Privacy Policy</Link>
          <a href="mailto:support@explify.app">Contact</a>
        </div>
        <p className="landing-footer-copy">
          A product of Lumen Innovations
        </p>
      </footer>
    </div>
  );
}
