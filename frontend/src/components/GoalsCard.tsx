export function GoalsCard() {
  return (
    <section className="panel goals-panel" aria-labelledby="goals-title">
      <span className="section-kicker">YOUR NEXT CHAPTER</span>
      <h2 id="goals-title">Put your goals first.</h2>
      <p>
        Review your actual holdings, valuation, allocation, and available risk evidence before
        adding interpretation or planning around financial goals.
      </p>
      <a className="secondary-cta" href="#/portfolio">
        <span>Explore my portfolio</span><span aria-hidden="true">→</span>
      </a>
    </section>
  );
}
