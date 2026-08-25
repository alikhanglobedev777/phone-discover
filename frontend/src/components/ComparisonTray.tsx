import type { Device } from "../types";

type Props = {
  devices: Device[];
  selectionCount: number;
  loading: boolean;
  onRemove: (slug: string) => void;
  onClear: () => void;
  onCompare: () => void;
};

export function ComparisonTray({ devices, selectionCount, loading, onRemove, onClear, onCompare }: Props) {
  if (!selectionCount) return null;
  return (
    <aside className="comparison-tray">
      <div className="comparison-summary">
        <strong>Compare phones</strong>
        <span className="muted">{selectionCount}/3 selected</span>
      </div>
      <div className="comparison-items">
        {devices.map((device) => (
          <button className="comparison-pill" key={device.slug} onClick={() => onRemove(device.slug)}>
            {device.primary_image_url && <img src={device.primary_image_url} alt="" />}
            <span>{device.name}</span> ×
          </button>
        ))}
        {loading && devices.length < selectionCount && <span className="comparison-loading">Loading…</span>}
      </div>
      <div className="comparison-actions">
        <button className="comparison-clear" type="button" onClick={onClear}>Clear</button>
        <button className="comparison-open" type="button" onClick={onCompare} disabled={devices.length < 2 || loading}>
          Compare now
        </button>
      </div>
    </aside>
  );
}
