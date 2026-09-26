type StatusBadgeProps = {
  status: string;
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const normalized = status.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  return <span className={`status-badge status-badge--${normalized}`}>{status}</span>;
}
