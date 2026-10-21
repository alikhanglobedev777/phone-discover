type Props = { onCompare: () => void };

export function SiteFooter({ onCompare }: Props) {
  return (
    <footer className="site-footer site-footer-new" aria-label="Website footer">
      <div className="footer-main">
        <div className="footer-about">
          <a href="#top" className="footer-brand-lockup" aria-label="Phone Discover home">
            <span className="footer-brand-icon" aria-hidden="true">P<span>.</span></span>
            <span>phone<strong>discover</strong></span>
          </a>
          <p>Find your next phone with clarity. Explore models, compare specifications, and understand the Pakistan price market without the guesswork.</p>
          <a href="#latest" className="footer-discover-link">See the latest phones <span aria-hidden="true">↗</span></a>
        </div>
        <div className="footer-link-column">
          <h3>Discover</h3>
          <a href="#latest">Latest phones</a>
          <a href="#catalog">All phones &amp; brands</a>
          <a href="#market">Pakistan price guide</a>
        </div>
        <div className="footer-link-column">
          <h3>Explore more</h3>
          <button type="button" onClick={onCompare}>Compare phones</button>
          <a href="#how-it-works">How it works</a>
          <a href="#top">Back to top ↑</a>
        </div>
      </div>
      <div className="footer-trust-strip" aria-label="Our catalog principles">
        <span><i aria-hidden="true">✓</i> Source-backed phone details</span>
        <span><i aria-hidden="true">✓</i> Transparent price evidence</span>
        <span><i aria-hidden="true">✓</i> Built for Pakistan</span>
      </div>
      <div className="footer-bottom">
        <span>© {new Date().getFullYear()} Phone Discover. Find your fit.</span>
        <p>PKR prices are observed asking prices, not guaranteed offers. Phone specifications, images and local availability may vary. Always verify seller, condition and PTA status.</p>
      </div>
    </footer>
  );
}
