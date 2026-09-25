export function GoalsCard() {
  return (
    <section className="panel goals-panel" id="portfolio" aria-labelledby="goals-title">
      <span className="section-kicker">YOUR NEXT CHAPTER</span>
      <h2 id="goals-title">Put your goals first.</h2>
      <p>Give every investment a purpose. Explore how contributions and time could shape your portfolio.</p>
      <div className="goal-links">
        <a href="#long-term-growth">
          <span className="goal-icon" aria-hidden="true">↗</span>
          <span><strong>Long-term growth</strong><small>Build with a consistent plan</small></span>
        </a>
        <a href="#income-planning">
          <span className="goal-icon" aria-hidden="true">◎</span>
          <span><strong>Income planning</strong><small>Understand the capital you need</small></span>
        </a>
      </div>
      <a className="secondary-cta" href="#portfolio">
        <span>Explore my portfolio</span><span aria-hidden="true">→</span>
      </a>
    </section>
  );
}
