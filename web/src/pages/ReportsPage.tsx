/**
 * Reports.
 *
 * Generate a report, read it in the browser, export it as CSV or JSON. The
 * catalogue on the left is served by the API rather than hardcoded here, so
 * the page cannot offer a report type the backend has no builder for.
 *
 * A stored report is a record of what was true when it ran. It is rendered
 * from the persisted document, never re-computed on open — a report whose
 * numbers change when you reopen it is not evidence of anything. That is also
 * why each report carries its window, its parameters, the account that ran it,
 * and how many of its records are synthetic.
 */

import { useState } from "react";

import { Unavailable } from "@/components/charts/Charts";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { Panel } from "@/components/ui/Panel";
import { AsyncBoundary, EmptyState } from "@/components/ui/StateBlock";
import {
  downloadReport,
  useGenerateReport,
  useReportTypes,
  useReports,
  type Report,
  type ReportSection,
  type ReportType,
} from "@/features/reports/api";
import { usePageHeader } from "@/hooks/usePageHeader";
import { formatRelativeTime, formatTimestamp } from "@/lib/format";

const WINDOWS = [
  { hours: 24, label: "24h" },
  { hours: 24 * 7, label: "7d" },
  { hours: 24 * 30, label: "30d" },
  { hours: 24 * 90, label: "90d" },
];

export function ReportsPage() {
  const types = useReportTypes();
  const history = useReports();
  const generate = useGenerateReport();

  const [selectedType, setSelectedType] = useState<ReportType>("DAILY");
  const [openId, setOpenId] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState<"csv" | "json" | null>(null);

  /** A window the user picked explicitly, or null to follow the report type. */
  const [chosenWindow, setChosenWindow] = useState<number | null>(null);

  /**
   * The window is derived rather than synchronised.
   *
   * Each report type declares the window it is designed to cover, and the
   * catalogue arrives asynchronously, so an effect copying the default into
   * state would both cascade a second render and briefly show the wrong
   * window. Deriving it means an untouched selector always reflects the
   * selected type, and picking a window pins it until the type changes.
   */
  const info = types.data?.find((entry) => entry.type === selectedType);
  const windowHours = chosenWindow ?? info?.default_window_hours ?? 24;

  const selectType = (type: ReportType) => {
    setSelectedType(type);
    setChosenWindow(null);
  };

  const open = history.data?.find((report) => report.id === openId) ?? generate.data ?? null;

  usePageHeader("Reports", "Generated road-safety reporting for operators and traffic authorities");

  const runReport = () => {
    setExportError(null);
    generate.mutate(
      { type: selectedType, window_hours: windowHours },
      { onSuccess: (report) => setOpenId(report.id) },
    );
  };

  const runExport = async (format: "csv" | "json") => {
    if (!open) return;
    setExportError(null);
    setExporting(format);
    try {
      await downloadReport(open.id, format);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "Export failed.");
    } finally {
      setExporting(null);
    }
  };

  return (
    <div className="flex h-full min-h-0">
      {/* ------------------------------------------------------------- sidebar */}
      <aside className="border-line bg-surface flex w-72 shrink-0 flex-col overflow-y-auto border-r">
        <div className="border-line-subtle border-b p-3">
          <h2 className="field-label">Generate</h2>

          <AsyncBoundary
            isLoading={types.isLoading}
            error={types.error}
            data={types.data}
            onRetry={() => void types.refetch()}
          >
            {(catalogue) => (
              <div className="space-y-1">
                {catalogue.map((entry) => (
                  <button
                    key={entry.type}
                    type="button"
                    onClick={() => selectType(entry.type)}
                    className={
                      selectedType === entry.type
                        ? "border-accent-line bg-accent-dim block w-full rounded-sm border px-2 py-1.5 text-left"
                        : "border-line-subtle hover:bg-surface-hover block w-full rounded-sm border px-2 py-1.5 text-left transition-colors"
                    }
                  >
                    <span
                      className={
                        selectedType === entry.type
                          ? "text-accent block text-xs font-semibold"
                          : "text-ink block text-xs font-medium"
                      }
                    >
                      {entry.label}
                    </span>
                    <span className="text-ink-subtle mt-0.5 block text-2xs leading-snug">
                      {entry.description}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </AsyncBoundary>

          <div className="mt-3">
            <span className="field-label">Window</span>
            <div className="border-line-strong flex overflow-hidden rounded-sm border">
              {WINDOWS.map((option) => (
                <button
                  key={option.hours}
                  type="button"
                  onClick={() => setChosenWindow(option.hours)}
                  className={
                    windowHours === option.hours
                      ? "bg-accent-dim text-accent flex-1 px-2 py-1 text-2xs font-semibold"
                      : "text-ink-muted hover:bg-surface-hover flex-1 px-2 py-1 text-2xs"
                  }
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <Button
            className="mt-3 w-full"
            size="sm"
            icon={<Icon name="report" size={13} />}
            loading={generate.isPending}
            onClick={runReport}
          >
            Generate report
          </Button>

          {generate.error ? (
            <p className="text-risk-critical mt-2 text-2xs">
              {generate.error instanceof Error ? generate.error.message : "Generation failed."}
            </p>
          ) : null}
        </div>

        {/* ------------------------------------------------------------ history */}
        <div className="min-h-0 flex-1 p-3">
          <h2 className="field-label">History</h2>
          <AsyncBoundary
            isLoading={history.isLoading}
            error={history.error}
            data={history.data}
            onRetry={() => void history.refetch()}
            emptyMessage="No reports generated yet."
            emptyHint="Pick a type and a window above, then generate one. Each run is stored with its parameters."
            loadingVariant="rows"
          >
            {(reports) => (
              <ul className="space-y-1">
                {reports.map((report) => (
                  <li key={report.id}>
                    <button
                      type="button"
                      onClick={() => setOpenId(report.id)}
                      className={
                        open?.id === report.id
                          ? "border-accent-line bg-accent-dim block w-full rounded-sm border px-2 py-1.5 text-left"
                          : "border-line-subtle hover:bg-surface-hover block w-full rounded-sm border px-2 py-1.5 text-left transition-colors"
                      }
                    >
                      <span className="text-ink block truncate text-xs font-medium">
                        {report.title}
                      </span>
                      <span className="text-ink-subtle mt-0.5 flex items-center gap-1.5 text-2xs">
                        <span className="mono">{formatRelativeTime(report.generated_at)}</span>
                        <span>·</span>
                        <span>{report.window_label}</span>
                        {report.demo_record_count > 0 ? (
                          <Badge tone="accent" className="ml-auto">
                            Demo
                          </Badge>
                        ) : null}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </AsyncBoundary>
        </div>
      </aside>

      {/* -------------------------------------------------------------- report */}
      <div className="min-w-0 flex-1 overflow-y-auto p-4">
        {open ? (
          <ReportView
            report={open}
            onExport={(format) => void runExport(format)}
            exporting={exporting}
            exportError={exportError}
          />
        ) : (
          <EmptyState
            icon={<Icon name="report" size={22} />}
            message="No report open"
            hint="Generate a report from the panel on the left, or pick one from the history. Reports are rendered from the stored document, so reopening one shows exactly what it said when it ran."
          />
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------- report */

function ReportView({
  report,
  onExport,
  exporting,
  exportError,
}: {
  report: Report;
  onExport: (format: "csv" | "json") => void;
  exporting: "csv" | "json" | null;
  exportError: string | null;
}) {
  return (
    <div className="space-y-3">
      <div className="border-line bg-surface rounded-sm border p-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-ink text-base font-semibold">{report.title}</h1>
            <p className="text-ink-muted mt-0.5 text-xs">{report.subtitle}</p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <Button
              size="sm"
              variant="secondary"
              icon={<Icon name="download" size={13} />}
              loading={exporting === "csv"}
              onClick={() => onExport("csv")}
            >
              CSV
            </Button>
            <Button
              size="sm"
              variant="secondary"
              icon={<Icon name="download" size={13} />}
              loading={exporting === "json"}
              onClick={() => onExport("json")}
            >
              JSON
            </Button>
          </div>
        </div>

        <dl className="border-line-subtle mt-3 grid grid-cols-2 gap-x-6 gap-y-2 border-t pt-3 sm:grid-cols-3 lg:grid-cols-5">
          <Field label="Generated" value={formatTimestamp(report.generated_at)} />
          <Field label="By" value={report.generated_by} />
          <Field label="Window" value={report.window_label} />
          <Field label="Records" value={report.record_count.toLocaleString()} />
          <Field
            label="Synthetic"
            value={report.demo_record_count.toLocaleString()}
            tone={report.demo_record_count > 0 ? "warn" : undefined}
          />
        </dl>

        <p className="text-ink-subtle mono border-line-subtle mt-2 border-t pt-2 text-2xs">
          {formatTimestamp(report.period_start)} → {formatTimestamp(report.period_end)}
        </p>

        {report.demo_record_count > 0 ? (
          <div className="border-line-strong bg-surface-raised mt-3 flex items-start gap-2 rounded-sm border px-2.5 py-2">
            <Icon name="info" size={13} className="text-ink-subtle mt-0.5 shrink-0" />
            <p className="text-ink-muted text-2xs leading-relaxed">
              <span className="text-ink font-semibold">
                {report.demo_record_count.toLocaleString()} of{" "}
                {report.record_count.toLocaleString()} records in this report are synthetic.
              </span>{" "}
              It is not an operational record of any real road, and the CSV and JSON exports carry
              the same warning in their header.
            </p>
          </div>
        ) : null}

        {exportError ? <p className="text-risk-critical mt-2 text-2xs">{exportError}</p> : null}
      </div>

      {report.sections.map((section) => (
        <SectionView key={section.title} section={section} />
      ))}
    </div>
  );
}

function SectionView({ section }: { section: ReportSection }) {
  return (
    <Panel title={section.title} meta={section.available ? `${section.rows.length} rows` : undefined} flush>
      {section.note ? (
        <p className="text-ink-subtle border-line-subtle border-b px-3 py-2 text-2xs leading-relaxed">
          {section.note}
        </p>
      ) : null}

      {!section.available ? (
        <div className="p-3">
          <Unavailable reason={section.unavailable_reason ?? "Could not be computed."} />
        </div>
      ) : section.rows.length === 0 ? (
        <p className="text-ink-subtle p-3 text-xs">No rows.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="border-line-strong border-b">
                {section.columns.map((column) => (
                  <th
                    key={column.key}
                    className={
                      column.numeric
                        ? "text-ink-subtle px-2.5 py-1.5 text-right text-2xs font-semibold tracking-wide uppercase"
                        : "text-ink-subtle px-2.5 py-1.5 text-left text-2xs font-semibold tracking-wide uppercase"
                    }
                  >
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {section.rows.map((row, index) => (
                <tr key={index} className="border-line-subtle border-b last:border-0">
                  {section.columns.map((column) => (
                    <td
                      key={column.key}
                      className={
                        column.numeric
                          ? "text-ink-muted px-2.5 py-1.5 text-right tabular-nums"
                          : "text-ink-muted px-2.5 py-1.5"
                      }
                    >
                      <Cell value={row[column.key]} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

/**
 * One cell.
 *
 * An absent value renders as a dash with a tooltip rather than as 0 or an
 * empty cell, so a reader can tell "not measured" from "measured as nothing".
 */
function Cell({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "") {
    return (
      <span className="text-ink-subtle" title="Not measured for this row.">
        —
      </span>
    );
  }
  if (value === "UNABLE TO DETERMINE") {
    return (
      <span className="text-ink-subtle text-2xs font-semibold tracking-wide uppercase">
        {value}
      </span>
    );
  }
  if (typeof value === "number") {
    return <>{Number.isInteger(value) ? value.toLocaleString() : value.toFixed(1)}</>;
  }
  if (typeof value === "boolean") return <>{value ? "yes" : "no"}</>;
  return <>{String(value)}</>;
}

function Field({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "warn";
}) {
  return (
    <div className="min-w-0">
      <dt className="field-label mb-0">{label}</dt>
      <dd
        className={
          tone === "warn"
            ? "text-risk-moderate mt-0.5 truncate text-xs font-semibold"
            : "text-ink mt-0.5 truncate text-xs"
        }
        title={value}
      >
        {value}
      </dd>
    </div>
  );
}
